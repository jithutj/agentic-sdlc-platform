"""Provider-neutral, bounded structured generation. Only a local mock is selectable."""
import asyncio
import json
import os
from time import monotonic
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True,
                              allow_inf_nan=False)


class LLMMessage(Contract):
    role: Literal["system", "user"]
    content: str = Field(min_length=1, max_length=12000, repr=False)


class LLMRequest(Contract):
    messages: tuple[LLMMessage, ...] = Field(min_length=1, max_length=8, repr=False)
    response_schema: dict = Field(repr=False)
    max_output_bytes: int = Field(ge=1, le=16384)
    timeout_seconds: float = Field(gt=0, le=10)


class LLMResponse(Contract):
    content: str = Field(repr=False)
    finish_reason: Literal["stop", "length"] = "stop"


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Adapters must support cancellation and must not log request/response bodies."""
        ...


class ProviderUnavailable(Exception):
    """Adapter signals a transient failure; gateway may retry within run allowance."""


class GatewayFailure(Exception):
    def __init__(self, code: str):
        # Only server-defined error codes may cross the agent/checkpoint boundary.
        self.code = code
        super().__init__(code)


class GatewayLimits(Contract):
    max_input_chars: int = Field(default=4000, ge=1, le=4000)
    max_output_bytes: int = Field(default=12000, ge=1, le=16384)
    max_attempts: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=1.0, ge=0.01, le=10)
    run_timeout_seconds: float = Field(default=3.0, ge=0.01, le=30)
    budget_units: int = Field(default=60000, ge=0, le=1000000)

    @classmethod
    def from_environment(cls):
        fields = {
            "max_input_chars": ("LLM_MAX_INPUT_CHARS", int),
            "max_output_bytes": ("LLM_MAX_OUTPUT_BYTES", int),
            "max_attempts": ("LLM_MAX_ATTEMPTS", int),
            "timeout_seconds": ("LLM_TIMEOUT_SECONDS", float),
            "run_timeout_seconds": ("LLM_RUN_TIMEOUT_SECONDS", float),
            "budget_units": ("LLM_RUN_BUDGET_UNITS", int),
        }
        try:
            return cls(**{key: convert(os.environ[name]) for key, (name, convert) in fields.items()
                          if name in os.environ})
        except (ValueError, ValidationError):
            raise GatewayFailure("invalid_configuration") from None


class GatewayUsage(Contract):
    attempts: int = Field(default=0, ge=0)
    reserved_units: int = Field(default=0, ge=0)


class BudgetLedger(Protocol):
    def reserve(self, units: int, limits: GatewayLimits) -> None: ...
    def usage(self) -> GatewayUsage: ...


class MemoryBudget:
    def __init__(self):
        self._usage = GatewayUsage()

    def usage(self) -> GatewayUsage:
        return self._usage

    def reserve(self, units: int, limits: GatewayLimits) -> None:
        if self._usage.attempts >= limits.max_attempts:
            raise GatewayFailure("retry_exhausted")
        if self._usage.reserved_units + units > limits.budget_units:
            raise GatewayFailure("budget_exceeded")
        self._usage = GatewayUsage(attempts=self._usage.attempts + 1,
                                   reserved_units=self._usage.reserved_units + units)


class MockLLMClient:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Fixed template only: never execute objective text or infer tool requests.
        objective = next(m.content for m in reversed(request.messages) if m.role == "user")
        excerpt = " ".join(objective.split())[:300]
        content = {
            "summary": f"Mock requirements draft: {excerpt}",
            "scope": [excerpt],
            "out_of_scope": ["Production deployment, real provider calls and external integrations."],
            "user_stories": [{"role": "requester", "goal": excerpt,
                              "benefit": "Review a specification before implementation."}],
            "acceptance_criteria": ["The proposed scope represents the stated objective.",
                                    "A human resolves open questions before implementation."],
            "assumptions": ["The objective is preliminary and requires human validation."],
            "open_questions": ["Who are the intended users?", "What constraints and validation rules apply?"],
        }
        return LLMResponse(content=json.dumps(content, ensure_ascii=False))


def configured_client() -> LLMClient:
    if os.environ.get("LLM_PROVIDER", "mock") != "mock":
        raise GatewayFailure("invalid_configuration")
    return MockLLMClient()


T = TypeVar("T", bound=BaseModel)


class LLMGateway:
    def __init__(self, client: LLMClient):
        self.client = client

    async def generate(self, messages: tuple[LLMMessage, ...], response_model: type[T],
                       limits: GatewayLimits, ledger: BudgetLedger) -> T:
        deadline = monotonic() + limits.run_timeout_seconds
        if sum(len(message.content) for message in messages if message.role == "user") > limits.max_input_chars:
            raise GatewayFailure("input_limit_exceeded")
        schema = response_model.model_json_schema()
        # Conservative normalized units: UTF-8 messages/schema bytes plus full output
        # allowance per attempt. Never rely on provider-reported usage or pricing.
        try:
            input_bytes = len(json.dumps({"messages": [m.model_dump() for m in messages],
                                         "schema": schema}, ensure_ascii=False).encode())
        except UnicodeError:
            raise GatewayFailure("input_limit_exceeded") from None
        units = input_bytes + limits.max_output_bytes
        last_error = "retry_exhausted"
        for _ in range(limits.max_attempts):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise GatewayFailure("execution_timeout")
            ledger.reserve(units, limits)
            # Budget persistence may consume time; do not start a call after deadline.
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise GatewayFailure("execution_timeout")
            timeout = min(limits.timeout_seconds, remaining)
            request = LLMRequest(messages=messages, response_schema=schema,
                                 max_output_bytes=limits.max_output_bytes, timeout_seconds=timeout)
            try:
                response = await asyncio.wait_for(self.client.complete(request), timeout=timeout)
            except TimeoutError:
                last_error = "provider_timeout"
                continue
            except ProviderUnavailable:
                last_error = "retry_exhausted"
                continue
            except ValidationError:
                raise GatewayFailure("invalid_output") from None
            except Exception:
                raise GatewayFailure("provider_failure") from None
            if not isinstance(response, LLMResponse) or response.finish_reason != "stop":
                raise GatewayFailure("invalid_output")
            try:
                output_bytes = len(response.content.encode())
            except UnicodeError:
                raise GatewayFailure("invalid_output") from None
            if output_bytes > limits.max_output_bytes:
                raise GatewayFailure("output_limit_exceeded")
            try:
                result = response_model.model_validate_json(response.content)
            except (ValidationError, ValueError):
                raise GatewayFailure("invalid_output") from None
            if monotonic() >= deadline:
                raise GatewayFailure("execution_timeout")
            return result
        if monotonic() >= deadline:
            raise GatewayFailure("execution_timeout")
        raise GatewayFailure(last_error)
