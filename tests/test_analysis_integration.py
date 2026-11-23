"""Synthetic mock-only analysis records in an explicitly opted-in local test DB."""
import asyncio
import json
import os
import subprocess
import sys
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.database import connection_parameters
from app.llm import (GatewayFailure, GatewayLimits, LLMGateway, LLMMessage,
                     MockLLMClient, ProviderUnavailable)
from app.llm_budget import PostgresBudget
from app.main import app
from app.models import AnalysisTask, Task
from app.requirements import Requirements
from app.workflow_store import ResumeDenied, WorkflowConflict, WorkflowNotFound, open_workflows

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("RUN_WORKFLOW_INTEGRATION") != "1",
    reason="Requires opted-in, migrated local workflow test database",
)]


@pytest.fixture(autouse=True)
def mock_configuration(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MAX_INPUT_CHARS", "LLM_MAX_OUTPUT_BYTES",
                 "LLM_MAX_ATTEMPTS", "LLM_TIMEOUT_SECONDS", "LLM_RUN_TIMEOUT_SECONDS",
                 "LLM_RUN_BUDGET_UNITS"):
        monkeypatch.delenv(name, raising=False)


def task(project_id=None, run_id=None):
    return AnalysisTask(project_id=project_id or f"analysis-{uuid4()}",
                        run_id=run_id or str(uuid4()), objective="Describe a local issue tracker")


def record_approval(pending):
    approval_id = str(uuid4())
    parameters = connection_parameters(read_only=False)
    parameters.update(user="postgres", password=os.environ["CHECKPOINT_TEST_ADMIN_PASSWORD"])
    with psycopg.connect(**parameters, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO workflow.approvals "
            "(approval_id, thread_id, checkpoint_id, state_digest, approver_id, expires_at) "
            "VALUES (%s,%s,%s,%s,'synthetic-local-reviewer',clock_timestamp()+interval '1 hour')",
            (approval_id, pending["thread_id"], pending["checkpoint_id"], pending["state_digest"]),
        )
    return approval_id


def test_analysis_checkpoint_interrupt_and_fresh_process_retrieval():
    original = task()
    response = TestClient(app).post("/analysis", json=original.model_dump(mode="json"))
    assert response.status_code == 200
    result = response.json()
    Requirements.model_validate(result["requirements"])
    identity = (original.project_id, original.run_id, result["thread_id"])
    with open_workflows() as workflows:
        assert workflows.read(*identity) == result
        snapshot = workflows.analysis_graph.get_state({"configurable": {"thread_id": result["thread_id"]}})
        assert snapshot.next == ("review",)
        payload = snapshot.tasks[0].interrupts[0].value
        assert payload["requirements"] == result["requirements"]
        assert payload["untrusted"] is True
        assert PostgresBudget(workflows.connection, result["thread_id"]).usage().model_dump() == result["llm_usage"]
    code = """import json,sys
from app.workflow_store import open_workflows
with open_workflows() as workflows:
    print(json.dumps(workflows.read(*sys.argv[1:])))
"""
    process = subprocess.run([sys.executable, "-c", code, *identity], check=True,
                             capture_output=True, text=True, timeout=20)
    assert json.loads(process.stdout) == result


def test_analysis_project_isolation_and_global_project_run_uniqueness():
    first, second = task(run_id="shared-run"), task(run_id="shared-run")
    with open_workflows() as workflows:
        a, b = workflows.create_analysis(first), workflows.create_analysis(second)
        assert a["thread_id"] != b["thread_id"]
        for identity in ((second.project_id, first.run_id, a["thread_id"]),
                         (first.project_id, "other", a["thread_id"]),
                         (first.project_id, first.run_id, b["thread_id"])):
            with pytest.raises(WorkflowNotFound):
                workflows.read(*identity)
        with pytest.raises(WorkflowConflict):
            workflows.create_analysis(first)
        with pytest.raises(WorkflowConflict):
            workflows.create(Task(project_id=first.project_id, run_id=first.run_id, objective="Other graph"))
        assert workflows.read(first.project_id, first.run_id, a["thread_id"]) == a


def test_analysis_server_approval_resumes_without_another_provider_call(monkeypatch):
    original = task()
    with open_workflows() as workflows:
        result = workflows.create_analysis(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        pending = workflows.pending_review(*identity)
        with pytest.raises(ResumeDenied):
            workflows.resume(*identity, str(uuid4()))
        approval_id = record_approval(pending)
        with pytest.raises(WorkflowNotFound):
            workflows.resume("other-project", original.run_id, result["thread_id"], approval_id)

    def forbidden():
        raise AssertionError("Review resume must not generate requirements again")

    monkeypatch.setattr("app.workflow_store.configured_client", forbidden)
    with open_workflows() as workflows:
        resumed = workflows.resume(*identity, approval_id)
        assert resumed["status"] == "human_reviewed"
        assert resumed["requirements"] == result["requirements"]
        assert resumed["llm_usage"] == result["llm_usage"]
        with pytest.raises(ResumeDenied):
            workflows.resume(*identity, approval_id)


def test_budget_reservations_survive_reconnection(monkeypatch):
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "1")
    original = task()
    with open_workflows() as workflows:
        result = workflows.create_analysis(original)
    with open_workflows() as workflows:
        ledger = PostgresBudget(workflows.connection, result["thread_id"])
        assert ledger.usage().model_dump() == result["llm_usage"]
        snapshot = workflows.analysis_graph.get_state({"configurable": {"thread_id": result["thread_id"]}})
        limits = GatewayLimits.model_validate(snapshot.values["gateway_limits"])
        with workflows._locked(result["thread_id"]):
            with pytest.raises(GatewayFailure, match="retry_exhausted"):
                asyncio.run(LLMGateway(MockLLMClient()).generate(
                    (LLMMessage(role="user", content=original.objective),), Requirements, limits, ledger))
        assert ledger.usage().model_dump() == result["llm_usage"]


def test_persisted_budget_rejection_never_reaches_review(monkeypatch):
    monkeypatch.setenv("LLM_RUN_BUDGET_UNITS", "0")
    original = task()
    response = TestClient(app).post("/analysis", json=original.model_dump(mode="json"))
    assert response.status_code == 429
    result = response.json()
    with open_workflows() as workflows:
        identity = (original.project_id, original.run_id, result["thread_id"])
        assert workflows.read(*identity)["analysis_error"] == "budget_exceeded"
        assert PostgresBudget(workflows.connection, result["thread_id"]).usage().attempts == 0
        with pytest.raises(ResumeDenied):
            workflows.pending_review(*identity)
        with pytest.raises(ResumeDenied):
            workflows.resume(*identity, str(uuid4()))


@pytest.mark.parametrize("failure", ["retry", "timeout", "schema", "schema_nul"])
def test_failed_generation_is_persisted_without_raw_provider_details(monkeypatch, failure):
    class Broken:
        async def complete(self, request):
            if failure == "timeout":
                await asyncio.sleep(10)
            if failure == "schema":
                from app.llm import LLMResponse
                return LLMResponse(content='{"sensitive":"synthetic-provider-details"}')
            if failure == "schema_nul":
                from app.llm import LLMResponse
                valid = await MockLLMClient().complete(request)
                data = json.loads(valid.content)
                data["summary"] = "\x00"
                return LLMResponse(content=json.dumps(data))
            raise ProviderUnavailable("synthetic-provider-details")

    monkeypatch.setattr("app.workflow_store.configured_client", lambda: Broken())
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "0.02")
    original = task()
    response = TestClient(app).post("/analysis", json=original.model_dump(mode="json"))
    assert response.status_code == (504 if failure == "timeout" else 502)
    result = response.json()
    assert result["requirements"] is None
    assert "synthetic-provider-details" not in response.text
    expected = {"retry": "retry_exhausted", "timeout": "provider_timeout",
                "schema": "invalid_output", "schema_nul": "invalid_output"}
    with open_workflows() as workflows:
        identity = (original.project_id, original.run_id, result["thread_id"])
        assert workflows.read(*identity)["analysis_error"] == expected[failure]
        ledger = PostgresBudget(workflows.connection, result["thread_id"])
        assert ledger.usage().attempts == (1 if failure.startswith("schema") else 2)
        checkpoint = workflows.analysis_graph.get_state({"configurable": {"thread_id": result["thread_id"]}})
        assert checkpoint.next == ()


def test_runtime_cannot_reset_or_edit_budget_reservations():
    with open_workflows() as workflows:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            workflows.connection.execute("UPDATE workflow.llm_attempts SET reserved_units=1 WHERE false")
        assert workflows.connection.execute(
            "SELECT has_table_privilege(current_user,'workflow.llm_attempts','DELETE') AS can_delete"
        ).fetchone()["can_delete"] is False


def test_original_draft_and_analysis_remain_separate_graphs():
    draft = task()
    with open_workflows() as workflows:
        result = workflows.create(Task(project_id=draft.project_id, run_id=draft.run_id,
                                       objective=draft.objective))
        identity = (draft.project_id, draft.run_id, result["thread_id"])
        assert "requirements" not in result
        assert workflows.read(*identity) == result
        assert workflows.pending_review(*identity)["checkpoint_id"]
