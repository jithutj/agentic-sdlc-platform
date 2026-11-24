import asyncio
import json
from time import monotonic

import pytest

from app.llm import (GatewayFailure, GatewayLimits, LLMGateway, LLMMessage, LLMRequest,
                     LLMResponse, MemoryBudget, MockLLMClient, ProviderUnavailable,
                     configured_client)
from app.requirements import Requirements

MESSAGES = (LLMMessage(role="user", content="Describe a local task tracker"),)


class FixedClient:
    def __init__(self, content, finish_reason="stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return LLMResponse(content=self.content, finish_reason=self.finish_reason)


class FailingClient:
    def __init__(self, failures=100):
        self.calls = 0
        self.failures = failures

    async def complete(self, request):
        self.calls += 1
        if self.calls <= self.failures:
            raise ProviderUnavailable("synthetic-sensitive-provider-details")
        return await MockLLMClient().complete(request)


class SlowClient:
    def __init__(self):
        self.calls = 0
        self.cancellations = 0

    async def complete(self, request):
        self.calls += 1
        try:
            await asyncio.sleep(10)
        finally:
            self.cancellations += 1


def generate(client, ledger=None, limits=None, messages=MESSAGES):
    return asyncio.run(LLMGateway(client).generate(
        messages, Requirements, limits or GatewayLimits(), ledger or MemoryBudget()))


def test_mock_is_deterministic_structured_and_offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No networking allowed")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    first = generate(MockLLMClient())
    assert generate(MockLLMClient()) == first
    assert "local task tracker" in first.summary
    assert set(first.model_dump()) == {"summary", "scope", "out_of_scope", "user_stories",
                                      "acceptance_criteria", "assumptions", "open_questions"}


@pytest.mark.parametrize("provider", ["openai", "claude", "litellm", "ollama", "unknown"])
def test_real_provider_selection_fails_closed(monkeypatch, provider):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    with pytest.raises(GatewayFailure, match="invalid_configuration"):
        configured_client()


def test_sensitive_content_is_absent_from_contract_repr():
    request = LLMRequest(messages=(LLMMessage(role="user", content="synthetic-sensitive-input"),),
                         response_schema={}, max_output_bytes=100, timeout_seconds=1)
    assert "synthetic-sensitive" not in repr(request)
    assert "synthetic-sensitive" not in repr(request.messages[0])
    assert "synthetic-sensitive" not in repr(LLMResponse(content="synthetic-sensitive-output"))


@pytest.mark.parametrize("content", ["not-json", "{}", "[]", '{"summary":false}',
                                     '{"summary":"synthetic-sensitive-output","approved":true}'])
def test_schema_failures_are_redacted_without_retries(content, caplog):
    client = FixedClient(content)
    ledger = MemoryBudget()
    with pytest.raises(GatewayFailure) as error:
        generate(client, ledger)
    assert str(error.value) == "invalid_output"
    assert client.calls == ledger.usage().attempts == 1
    assert "synthetic-sensitive" not in caplog.text


def test_extra_fields_and_wrong_nested_types_are_rejected():
    good = generate(MockLLMClient()).model_dump()
    for bad in (dict(good, approved=True), dict(good, user_stories=["invalid"]),
                dict(good, summary="   "), dict(good, scope=[])):
        with pytest.raises(GatewayFailure, match="invalid_output"):
            generate(FixedClient(json.dumps(bad)))


@pytest.mark.parametrize("text", ["\x00", "\ud800"])
def test_invalid_postgres_text_in_escaped_json_is_rejected(text):
    good = generate(MockLLMClient()).model_dump()
    with pytest.raises(GatewayFailure, match="invalid_output"):
        generate(FixedClient(json.dumps(dict(good, summary=text))))


def test_transient_retry_succeeds_within_reserved_budget():
    ledger = MemoryBudget()
    client = FailingClient(failures=1)
    assert generate(client, ledger).scope
    assert ledger.usage().attempts == client.calls == 2
    assert 0 < ledger.usage().reserved_units <= GatewayLimits().budget_units


def test_retry_exhaustion_keeps_all_attempts_charged(caplog):
    client, ledger = FailingClient(), MemoryBudget()
    with pytest.raises(GatewayFailure, match="retry_exhausted"):
        generate(client, ledger)
    assert client.calls == ledger.usage().attempts == 2
    assert "synthetic-sensitive" not in caplog.text


def test_provider_timeout_cancels_call_and_returns_promptly():
    client = SlowClient()
    started = monotonic()
    with pytest.raises(GatewayFailure, match="provider_timeout"):
        generate(client, limits=GatewayLimits(max_attempts=1, timeout_seconds=0.02))
    assert monotonic() - started < 1
    assert client.calls == client.cancellations == 1


def test_total_deadline_bounds_multiple_attempts():
    client = SlowClient()
    started = monotonic()
    with pytest.raises(GatewayFailure, match="execution_timeout"):
        generate(client, limits=GatewayLimits(max_attempts=3, timeout_seconds=0.03,
                                             run_timeout_seconds=0.04))
    assert monotonic() - started < 1
    assert client.calls <= 2
    assert client.calls == client.cancellations


def test_zero_budget_prevents_provider_execution():
    client, ledger = FailingClient(), MemoryBudget()
    with pytest.raises(GatewayFailure, match="budget_exceeded"):
        generate(client, ledger, GatewayLimits(budget_units=0))
    assert client.calls == ledger.usage().attempts == 0


def test_retry_reservation_cannot_exceed_remaining_budget():
    ledger = MemoryBudget()
    client = FailingClient(failures=1)
    generate(client, ledger)
    one_attempt_units = ledger.usage().reserved_units // 2
    restricted = MemoryBudget()
    client = FailingClient()
    with pytest.raises(GatewayFailure, match="budget_exceeded"):
        generate(client, restricted, GatewayLimits(budget_units=one_attempt_units))
    assert client.calls == 1
    assert restricted.usage().reserved_units == one_attempt_units


def test_input_limit_rejects_before_reserving():
    client, ledger = FailingClient(), MemoryBudget()
    with pytest.raises(GatewayFailure, match="input_limit_exceeded"):
        generate(client, ledger, GatewayLimits(max_input_chars=1))
    assert client.calls == ledger.usage().attempts == 0


def test_output_limit_counts_utf8_bytes():
    client = FixedClient("é" * 40)
    with pytest.raises(GatewayFailure, match="output_limit_exceeded"):
        generate(client, limits=GatewayLimits(max_output_bytes=64))


def test_truncated_output_is_not_accepted():
    with pytest.raises(GatewayFailure, match="invalid_output"):
        generate(FixedClient("{}", finish_reason="length"))


@pytest.mark.parametrize("name,value", [("LLM_MAX_ATTEMPTS", "4"), ("LLM_MAX_ATTEMPTS", "0"),
    ("LLM_TIMEOUT_SECONDS", "nan"), ("LLM_RUN_BUDGET_UNITS", "-1"), ("LLM_MAX_INPUT_CHARS", "4001")])
def test_invalid_policy_configuration_is_safe(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(GatewayFailure, match="invalid_configuration"):
        GatewayLimits.from_environment()
