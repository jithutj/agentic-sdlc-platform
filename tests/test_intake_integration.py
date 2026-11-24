"""Real PostgreSQL and LangGraph, with synthetic contracts; no Linear requests."""
from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import psycopg
import pytest

from app.workflow_store import open_workflows, WorkflowConflict
from windmill.red5_linear_dispatch import contract

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("RUN_WORKFLOW_INTEGRATION") != "1", reason="Requires migrated local PostgreSQL")]


def test_intake_and_mock_analysis_checkpoints_coexist_after_reconnect(monkeypatch):
    from app.models import AnalysisTask
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    payload = contract() | {"project_id": "test-" + str(uuid4())}
    task = AnalysisTask(project_id=payload["project_id"], run_id=str(uuid4()),
                        objective="Describe a synthetic local issue tracker")
    with open_workflows() as workflows:
        analysis = workflows.create_analysis(task)
        intake = workflows.intake(payload, "synthetic-merged-main-001", {})
        pending = [workflows.pending_review(payload["project_id"], state["run_id"], state["thread_id"])
                   for state in (analysis, intake)]
    with open_workflows() as workflows:
        assert workflows.read(task.project_id, task.run_id, analysis["thread_id"]) == analysis
        assert analysis["requirements"] is not None
        assert workflows.intake(payload, "synthetic-merged-main-001", {}) == intake
        assert [workflows.pending_review(payload["project_id"], state["run_id"], state["thread_id"])
                for state in (analysis, intake)] == pending
        assert all(state["status"] == "awaiting_human_review" for state in (analysis, intake))


def test_retry_across_connections_and_conflict():
    payload = contract() | {"project_id": "test-" + str(uuid4())}
    with open_workflows() as workflows:
        first = workflows.intake(payload, "synthetic-key-001", {"identity": "synthetic"})
        state = workflows.read(payload["project_id"], first["run_id"], first["thread_id"])
        assert "Plan:" in state["draft"] and "QA:" in state["draft"]
        assert "Codex execution and repository changes disabled" in state["draft"]
        before = workflows.pending_review(payload["project_id"], first["run_id"], first["thread_id"])
    with open_workflows() as workflows:
        assert workflows.intake(payload, "synthetic-key-001", {"identity": "synthetic"}) == first
        assert workflows.intake(payload, "different-key-001", {"identity": "synthetic"}) == first
        for changed, scope in ((payload | {"objective": "Changed objective"}, {"identity": "synthetic"}),
                               (payload, {"identity": "changed"})):
            with pytest.raises(WorkflowConflict):
                workflows.intake(changed, "synthetic-key-001", scope)
        assert workflows.pending_review(payload["project_id"], first["run_id"], first["thread_id"]) == before
        assert first["status"] == "awaiting_human_review"
        for flag in ("approved", "codex_executed", "git_write_performed"):
            assert first[flag] is False


def test_concurrent_different_keys_cannot_duplicate_event():
    payload = contract() | {"project_id": "test-" + str(uuid4())}

    def intake(key):
        with open_workflows() as workflows:
            return workflows.intake(payload, key, {})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(intake, ["synthetic-key-001", "synthetic-key-002"]))
    assert results[0] == results[1]


def test_runtime_cannot_change_or_delete_intake_registry():
    with open_workflows() as workflows:
        for sql in ("UPDATE workflow.intake_events SET payload_digest='forged' WHERE false",
                    "DELETE FROM workflow.intake_events WHERE false"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                workflows.connection.execute(sql)


def test_platform_role_cannot_connect_to_windmill():
    from app.database import connection_parameters
    params = connection_parameters()
    params["dbname"] = "windmill"
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(**params)


def test_windmill_role_cannot_connect_to_platform():
    from app.database import connection_parameters
    params = connection_parameters()
    params.update(user="windmill_login", password=os.environ["WINDMILL_TEST_DB_PASSWORD"])
    with psycopg.connect(**(params | {"dbname": "windmill"})) as connection:
        assert connection.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == (False, False, False)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(**params)
