from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import database
from app.main import app


@pytest.fixture
def configured(monkeypatch):
    for name, value in {"DB_HOST": "db", "DB_NAME": "demo", "DB_USER": "demo",
                        "DB_PASSWORD": "synthetic-test-only", "DB_PORT": "5432",
                        "DB_CONNECT_TIMEOUT": "3"}.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("name,value", [
    ("DB_HOST", ""), ("DB_HOST", "db,other"), ("DB_HOST", "db other"),
    ("DB_PASSWORD", ""), ("DB_CONNECT_TIMEOUT", "0"),
    ("DB_CONNECT_TIMEOUT", "11"), ("DB_CONNECT_TIMEOUT", "bad"),
    ("DB_PORT", "0"), ("DB_PORT", "65536"),
])
def test_invalid_config_does_not_connect(configured, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    connect = MagicMock()
    monkeypatch.setattr(database.psycopg, "connect", connect)
    assert database.database_ready() is False
    connect.assert_not_called()


@pytest.mark.parametrize("row,expected", [((1, "0.8.7"), True), (None, False)])
def test_probe_closes_connection_and_checks_extension(configured, monkeypatch, row, expected):
    connect = MagicMock()
    connection = connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = row
    monkeypatch.setattr(database.psycopg, "connect", connect)
    assert database.database_ready() is expected
    parameters = connect.call_args.kwargs
    assert parameters["connect_timeout"] == 3
    assert parameters["port"] == 5432
    assert "statement_timeout=3000" in parameters["options"]
    assert "default_transaction_read_only=on" in parameters["options"]
    connect.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("during_query", [False, True])
def test_db_health_redacts_driver_errors(configured, monkeypatch, during_query):
    connect = MagicMock()
    error = psycopg.OperationalError("synthetic-test-only connection details")
    if during_query:
        connect.return_value.__enter__.return_value.execute.side_effect = error
    else:
        connect.side_effect = error
    monkeypatch.setattr(database.psycopg, "connect", connect)
    client = TestClient(app)
    response = client.get("/db-health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "synthetic-test-only" not in response.text
    assert client.get("/health").status_code == 200
    assert client.post("/draft", json={"project_id": "demo", "run_id": "r1",
                                       "objective": "Draft"}).status_code == 200


def test_db_health_success(monkeypatch):
    monkeypatch.setattr("app.main.database_ready", lambda: True)
    response = TestClient(app).get("/db-health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
