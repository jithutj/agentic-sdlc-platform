import json

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.llm import LLMResponse

BODY = {"project_id": "local", "run_id": "r1", "objective": "Track local tasks"}


def test_analysis_is_an_untrusted_draft_and_draft_api_is_unchanged():
    client = TestClient(app)
    result = client.post("/analysis", json=BODY)
    assert result.status_code == 200
    state = result.json()
    assert state["status"] == "awaiting_human_review"
    assert state["draft"] == "UNTRUSTED REQUIREMENTS DRAFT"
    assert state["llm_usage"]["attempts"] == 1
    assert state["requirements"]["user_stories"]
    original = client.post("/draft", json=BODY).json()
    assert original["draft"] == "DRAFT ONLY: Track local tasks"
    assert "requirements" not in original


def test_review_interrupt_contains_the_full_requirements():
    from langgraph.checkpoint.memory import InMemorySaver
    from app.analysis_workflow import build_analysis_graph
    from app.llm import GatewayLimits, MemoryBudget, MockLLMClient
    from app.models import AnalysisTask
    from app.requirements import analyze
    from app.workflow_store import initial_analysis_state

    ledger = MemoryBudget()
    graph = build_analysis_graph(InMemorySaver(), lambda state: analyze(state, MockLLMClient(), ledger))
    state = initial_analysis_state(AnalysisTask(**BODY), "test-thread", GatewayLimits())
    result = graph.invoke(state, {"configurable": {"thread_id": "test-thread"}})
    payload = result["__interrupt__"][0].value
    assert payload["requirements"] == result["requirements"]
    assert payload["untrusted"] is True


@pytest.mark.parametrize("extra", [{"approved": True}, {"thread_id": "caller-thread"},
                                  {"budget_units": 1000000}, {"provider": "openai"}])
def test_caller_cannot_override_identity_limits_provider_or_approval(extra):
    result = TestClient(app).post("/analysis", json=dict(BODY, **extra))
    assert result.status_code == 422
    assert result.json() == {"status": "invalid_analysis_request"}


def test_a0_local_draft_policy_denies_analysis():
    result = TestClient(app).post("/analysis", json=dict(BODY, level="A0"))
    assert result.status_code == 403
    assert result.json() == {"status": "analysis_denied"}


def test_invalid_request_never_echoes_sensitive_input(caplog):
    result = TestClient(app).post("/analysis", json=dict(BODY, objective="synthetic-sensitive-" * 300))
    assert result.status_code == 422
    assert "synthetic-sensitive" not in result.text + caplog.text


def test_body_limit_covers_chunked_requests_before_json_parsing():
    response = TestClient(app).post("/analysis", content=iter([b"a" * 20000, b"b" * 20000]),
                                    headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"status": "analysis_input_too_large"}


@pytest.mark.parametrize("objective", [" ", "\ud800", "\x00"])
def test_blank_and_invalid_unicode_are_rejected(objective):
    response = TestClient(app).post("/analysis", content=json.dumps(dict(BODY, objective=objective)),
                                    headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_budget_rejection_has_no_requirements(monkeypatch):
    monkeypatch.setenv("LLM_RUN_BUDGET_UNITS", "0")
    result = TestClient(app).post("/analysis", json=BODY)
    assert result.status_code == 429
    assert result.json()["requirements"] is None
    assert result.json()["llm_usage"]["attempts"] == 0
    assert result.json()["analysis_error"] == "budget_exceeded"


def test_unknown_provider_leaves_original_draft_usable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    client = TestClient(app)
    result = client.post("/analysis", json=BODY)
    assert result.status_code == 503
    assert result.json() == {"status": "analysis_unavailable"}
    assert client.post("/draft", json=BODY).status_code == 200


def test_malformed_provider_output_does_not_leak_to_api_or_logs(monkeypatch, caplog):
    class Malformed:
        async def complete(self, request):
            return LLMResponse(content='{"secret":"synthetic-sensitive-output"}')

    monkeypatch.setattr("app.workflow_store.configured_client", lambda: Malformed())
    result = TestClient(app).post("/analysis", json=BODY)
    assert result.status_code == 502
    assert result.json()["analysis_error"] == "invalid_output"
    assert result.json()["requirements"] is None
    assert "synthetic-sensitive" not in result.text + caplog.text


def test_provider_exception_is_redacted(monkeypatch, caplog):
    class Broken:
        async def complete(self, request):
            raise RuntimeError("synthetic-sensitive-provider-error")

    monkeypatch.setattr("app.workflow_store.configured_client", lambda: Broken())
    response = TestClient(app).post("/analysis", json=BODY)
    assert response.status_code == 502
    assert response.json()["analysis_error"] == "provider_failure"
    assert "synthetic-sensitive" not in response.text + caplog.text


@pytest.mark.parametrize("path", ["/analysis/resume", "/analysis/approve", "/resume", "/approvals"])
def test_analysis_does_not_add_public_resume_or_approval(path):
    assert TestClient(app).post(path, json={"approved": True}).status_code == 404
