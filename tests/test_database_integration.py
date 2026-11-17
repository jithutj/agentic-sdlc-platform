"""Opt-in, read-only tests against the initialized Compose database."""
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.database import connection_parameters
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("RUN_DB_INTEGRATION") != "1",
    reason="Set RUN_DB_INTEGRATION=1 with a configured database",
)]


def test_real_db_health():
    response = TestClient(app).get("/db-health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_vector_and_runtime_role():
    with psycopg.connect(**connection_parameters()) as connection:
        assert connection.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector").fetchone() == (1.0,)
        assert connection.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (False, False, False)
        assert connection.execute(
            "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
        ).fetchone() == (False,)


def test_bad_password_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "deliberately-invalid-integration-test")
    response = TestClient(app).get("/db-health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
