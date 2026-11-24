"""Offline boundary tests. Linear transport and workflow storage are explicit fakes."""
from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.main import app
from windmill.red5_linear_dispatch import contract, IntegrationUnavailable, ScopeDenied

TOKEN = "synthetic-intake-test-token-at-least-32-characters"
HEADERS = {"X-Pilot-Token": TOKEN, "Idempotency-Key": "red6-test-event-001"}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("PILOT_INTAKE_TOKEN", TOKEN)
    monkeypatch.setenv("WORKFLOW_PERSISTENCE", "postgres")
    monkeypatch.setenv("LINEAR_READ_API_KEY", "synthetic-read-only-key")
    for name in ("WORKSPACE_ID", "TEAM_ID", "ISSUE_UUID"):
        monkeypatch.setenv("PILOT_LINEAR_" + name, str(uuid4()))
    monkeypatch.setenv("PILOT_LINEAR_PROJECT_ID", "none")
    lookup = Mock()
    monkeypatch.setattr("app.intake.lookup", lookup)
    store = Mock()
    store.intake.return_value = {"run_id": "synthetic", "status": "awaiting_human_review"}

    @contextmanager
    def opened():
        yield store

    monkeypatch.setattr("app.intake.open_workflows", opened)
    return TestClient(app), lookup, store


def test_valid_intake_checks_linear_before_store(configured):
    client, lookup, store = configured
    assert client.post("/v1/intake", json=contract(), headers=HEADERS).status_code == 200
    lookup.assert_called_once()
    store.intake.assert_called_once()


@pytest.mark.parametrize("token", [None, "wrong", "", "é"])
def test_authentication_precedes_parsing_and_storage(configured, token):
    client, lookup, store = configured
    headers = {} if token is None else {"X-Pilot-Token": token}
    # httpx forbids non-ASCII header strings; bytes exercise hostile input.
    if token == "é":
        headers = {b"X-Pilot-Token": token.encode()}
    response = client.post("/v1/intake", content=b"not-json", headers=headers)
    assert response.status_code == 401
    lookup.assert_not_called()
    store.intake.assert_not_called()


def test_missing_server_token_fails_closed(configured, monkeypatch):
    monkeypatch.delenv("PILOT_INTAKE_TOKEN")
    assert configured[0].post("/v1/intake", json=contract(), headers=HEADERS).status_code == 401


@pytest.mark.parametrize("field,value,status", [
    ("project_id", "quick-menu-order", 403), ("repository", "jithutj/other", 403),
    ("issue_id", "RED-6", 403), ("operation", "github:push", 422),
    ("authorization", "A2", 422), ("approved", True, 422),
    ("thread_id", "caller", 422), ("shell_command", "echo untrusted", 422),
    ("objective", 1, 422), ("objective", "bad\x00objective", 422),
])
def test_scope_schema_and_self_approval_denied(configured, field, value, status):
    client, lookup, store = configured
    response = client.post("/v1/intake", json=contract() | {field: value}, headers=HEADERS)
    assert response.status_code == status
    assert str(value) not in response.text
    lookup.assert_not_called()
    store.intake.assert_not_called()


@pytest.mark.parametrize("key", ["x", "bad key value", "x" * 129])
def test_invalid_idempotency(configured, key):
    assert configured[0].post("/v1/intake", json=contract(),
                              headers=HEADERS | {"Idempotency-Key": key}).status_code == 400


@pytest.mark.parametrize("error,status", [(ScopeDenied(), 403), (IntegrationUnavailable(), 503)])
def test_linear_failure_never_starts_graph(configured, error, status):
    client, lookup, store = configured
    lookup.side_effect = error
    assert client.post("/v1/intake", json=contract(), headers=HEADERS).status_code == status
    store.intake.assert_not_called()


def test_intake_requires_postgres(configured, monkeypatch):
    monkeypatch.setenv("WORKFLOW_PERSISTENCE", "memory")
    assert configured[0].post("/v1/intake", json=contract(), headers=HEADERS).status_code == 503
    configured[2].intake.assert_not_called()


def test_body_limit_and_redacted_errors(configured):
    response = configured[0].post("/v1/intake", content=b"x" * 8193, headers=HEADERS)
    assert response.status_code == 413
    response = configured[0].post("/v1/intake", json=contract() | {"secret": "synthetic-secret"}, headers=HEADERS)
    assert response.status_code == 422
    assert "synthetic-secret" not in response.text


@pytest.mark.parametrize("path", ["/draft", "/analysis", "/analysis/", "/docs", "/openapi.json", "/approve", "/resume"])
def test_private_listener_exposes_only_intake_and_health(configured, monkeypatch, path):
    monkeypatch.setenv("LOCAL_DEMO_ROUTES", "false")
    assert configured[0].post(path, json={}).status_code == 404
    assert configured[0].get("/health").status_code == 200


def test_missing_trusted_identity_never_calls_linear(configured, monkeypatch):
    monkeypatch.delenv("PILOT_LINEAR_WORKSPACE_ID")
    assert configured[0].post("/v1/intake", json=contract(), headers=HEADERS).status_code == 503
    configured[1].assert_not_called()
