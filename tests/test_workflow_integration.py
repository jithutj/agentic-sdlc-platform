"""Additive synthetic runs in an explicitly opted-in local test database; no cleanup deletes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
import subprocess
import sys
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.database import connection_parameters
from app.main import app
from app.models import Task
from app.workflow_store import (ResumeDenied, WorkflowConflict, WorkflowNotFound,
                                WorkflowStateError, open_workflows)

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("RUN_WORKFLOW_INTEGRATION") != "1",
    reason="Requires RUN_WORKFLOW_INTEGRATION=1 and migrated local test database",
)]


def task(project_id=None, run_id=None):
    return Task(project_id=project_id or f"test-{uuid4()}", run_id=run_id or str(uuid4()),
                objective="Synthetic checkpoint test")


@contextmanager
def admin():
    parameters = connection_parameters(read_only=False)
    parameters.update(user="postgres", password=os.environ["CHECKPOINT_TEST_ADMIN_PASSWORD"])
    with psycopg.connect(**parameters, autocommit=True) as connection:
        yield connection


def approval(pending, *, expired=False, **overrides):
    # Only tests provision approval records. Production issuance/authentication is deferred.
    fields = dict(pending, approval_id=str(uuid4()))
    fields.update(overrides)
    with admin() as connection:
        connection.execute(
            "INSERT INTO workflow.approvals "
            "(approval_id,thread_id,checkpoint_id,state_digest,approver_id,created_at,expires_at) "
            "VALUES (%s,%s,%s,%s,'local-test-operator',clock_timestamp()-interval '2 hours',"
            "clock_timestamp() + %s::interval)",
            (fields["approval_id"], fields["thread_id"], fields["checkpoint_id"],
             fields["state_digest"], "-1 hour" if expired else "1 hour"),
        )
    return fields["approval_id"]


def test_persisted_interrupt_and_fresh_process_lookup():
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        pending = workflows.pending_review(original.project_id, original.run_id, result["thread_id"])
        assert pending["checkpoint_id"]
    code = """
import json, sys
from app.workflow_store import open_workflows
with open_workflows() as workflows:
    print(json.dumps(workflows.read(*sys.argv[1:])))
"""
    process = subprocess.run([sys.executable, "-c", code, original.project_id,
                              original.run_id, result["thread_id"]],
                             capture_output=True, text=True, timeout=20, check=True)
    assert json.loads(process.stdout) == result


def test_project_run_and_opaque_thread_isolation():
    first, second = task(run_id="same-run"), task(run_id="same-run")
    with open_workflows() as workflows:
        a, b = workflows.create(first), workflows.create(second)
        assert a["thread_id"] != b["thread_id"]
        assert workflows.read(first.project_id, first.run_id, a["thread_id"]) == a
        for project_id, run_id, handle in (
            (second.project_id, first.run_id, a["thread_id"]),
            (first.project_id, "other-run", a["thread_id"]),
            (first.project_id, first.run_id, b["thread_id"]),
            (first.project_id, first.run_id, "invalid"),
        ):
            with pytest.raises(WorkflowNotFound):
                workflows.read(project_id, run_id, handle)
        with pytest.raises(WorkflowConflict):
            workflows.create(first.model_copy(update={"objective": "Attempted overwrite"}))
        assert workflows.read(first.project_id, first.run_id, a["thread_id"]) == a


def test_http_create_is_persistent_and_duplicate_never_returns_state():
    original = task()
    client = TestClient(app)
    response = client.post("/draft", json=original.model_dump(mode="json"))
    assert response.status_code == 200
    result = response.json()
    with open_workflows() as workflows:
        assert workflows.read(original.project_id, original.run_id, result["thread_id"]) == result
    duplicate = client.post("/draft", json=original.model_dump(mode="json"))
    assert duplicate.status_code == 409
    assert duplicate.json() == {"status": "run_already_exists"}


def test_valid_server_approval_resumes_once_after_reconnect():
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        approval_id = approval(workflows.pending_review(*identity))
    with open_workflows() as workflows:
        assert workflows.resume(*identity, approval_id)["status"] == "human_reviewed"
    with open_workflows() as workflows:
        assert workflows.read(*identity)["status"] == "human_reviewed"
        with pytest.raises(ResumeDenied):
            workflows.resume(*identity, approval_id)


@pytest.mark.parametrize("invalid", ["missing", "expired", "checkpoint", "digest", "thread", "flag"])
def test_invalid_approvals_cannot_resume(invalid):
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        pending = workflows.pending_review(*identity)
        if invalid == "missing":
            approval_id = str(uuid4())
        elif invalid == "flag":
            approval_id = True
        elif invalid == "thread":
            other = task()
            other_state = workflows.create(other)
            approval_id = approval(workflows.pending_review(other.project_id, other.run_id,
                                                            other_state["thread_id"]))
        else:
            overrides = {"checkpoint_id": "wrong"} if invalid == "checkpoint" else {}
            if invalid == "digest":
                overrides["state_digest"] = "wrong"
            approval_id = approval(pending, expired=invalid == "expired", **overrides)
        with pytest.raises(ResumeDenied):
            workflows.resume(*identity, approval_id)
        assert workflows.pending_review(*identity) == pending


def test_cross_project_resume_denied_with_real_approval():
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        approval_id = approval(workflows.pending_review(*identity))
        with pytest.raises(WorkflowNotFound):
            workflows.resume("other-project", original.run_id, result["thread_id"], approval_id)
        assert workflows.read(*identity)["status"] == "awaiting_human_review"


def test_runtime_cannot_migrate_issue_approvals_or_change_identity():
    with open_workflows() as workflows:
        for query in (
            "CREATE TABLE workflow.forbidden (id int)",
            "INSERT INTO workflow.approvals (approval_id) VALUES ('forbidden')",
            "UPDATE workflow.runs SET project_id='forbidden' WHERE false",
            "UPDATE workflow.approvals SET approver_id='forbidden' WHERE false",
            "UPDATE workflow.approval_uses SET reserved_at=clock_timestamp() WHERE false",
            "SELECT * FROM workflow.checkpoint_migrations",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                workflows.connection.execute(query)


def test_concurrent_resume_consumes_only_once():
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        approval_id = approval(workflows.pending_review(*identity))

    def resume():
        with open_workflows() as workflows:
            try:
                return workflows.resume(*identity, approval_id)["status"]
            except ResumeDenied:
                return "denied"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: resume(), range(2))) == ["denied", "human_reviewed"]


def test_crash_after_reservation_fails_closed(monkeypatch):
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        approval_id = approval(workflows.pending_review(*identity))

        def crash(*args, **kwargs):
            raise RuntimeError("Simulated process failure")

        monkeypatch.setattr(workflows.graph, "invoke", crash)
        with pytest.raises(RuntimeError):
            workflows.resume(*identity, approval_id)
    with open_workflows() as workflows:
        with pytest.raises(ResumeDenied):
            workflows.resume(*identity, approval_id)
        assert workflows.read(*identity)["status"] == "awaiting_human_review"


def test_checkpoint_identity_tampering_is_detected():
    original = task()
    with open_workflows() as workflows:
        result = workflows.create(original)
        identity = (original.project_id, original.run_id, result["thread_id"])
        # Trusted-code corruption simulation; no raw checkpoint/update route exists.
        workflows.graph.update_state({"configurable": {"thread_id": result["thread_id"]}},
                                     {"project_id": "wrong-project"})
        with pytest.raises(WorkflowStateError):
            workflows.read(*identity)
