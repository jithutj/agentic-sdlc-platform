from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.main import app
from app.models import Task
from app.workflow import build_graph
from app.workflow_store import initial_state, preview


def test_genuine_interrupt_survives_graph_reconstruction():
    saver = InMemorySaver()
    task = Task(project_id="demo", run_id="r1", objective="Draft an API")
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = build_graph(saver).invoke(initial_state(task, thread_id), config)
    assert result["__interrupt__"][0].value["kind"] == "human_review"
    snapshot = build_graph(saver).get_state(config)
    assert snapshot.next == ("review",)
    assert snapshot.tasks[0].interrupts
    assert snapshot.values["status"] == "awaiting_human_review"


def test_preview_preserves_response_and_hides_internal_objects():
    result = preview(Task(project_id="p", run_id="r", objective="Example"))
    assert result["draft"] == "DRAFT ONLY: Example"
    assert result["status"] == "awaiting_human_review"
    assert set(result) == {"project_id", "run_id", "objective", "draft", "status", "thread_id"}


@pytest.mark.parametrize("path", ["/resume", "/approve", "/approvals", "/runs/r/resume", "/draft/resume"])
def test_no_http_approval_or_resume_surface(path):
    response = TestClient(app).post(path, json={"approved": True, "project_id": "p"})
    assert response.status_code == 404


def test_caller_approval_flags_cannot_resume():
    response = TestClient(app).post("/draft", json={
        "project_id": "p", "run_id": "r", "objective": "Example",
        "approved": True, "approval_id": str(uuid4()), "thread_id": str(uuid4()),
    })
    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_human_review"


def test_postgres_failure_is_redacted_and_never_falls_back(monkeypatch):
    monkeypatch.setenv("WORKFLOW_PERSISTENCE", "postgres")

    @contextmanager
    def unavailable():
        raise psycopg.OperationalError("synthetic secret and connection details")
        yield

    monkeypatch.setattr("app.main.open_workflows", unavailable)
    client = TestClient(app)
    response = client.post("/draft", json={"project_id": "p", "run_id": "r", "objective": "Example"})
    assert response.status_code == 503
    assert response.json() == {"status": "workflow_unavailable"}
    assert client.get("/health").json()["external_writes"] is False


def test_unknown_persistence_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("WORKFLOW_PERSISTENCE", "invalid")
    response = TestClient(app).post("/draft", json={"project_id": "p", "run_id": "r", "objective": "Example"})
    assert response.status_code == 503
