"""Offline preflight diagnostics; never start services, fetch secrets or call Linear."""
import json
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from scripts import setup_check as checker


@pytest.fixture
def ready(monkeypatch, tmp_path):
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker.shutil, "which", lambda _: "/test/docker")
    (tmp_path / "windmill").mkdir()
    (tmp_path / "windmill/red5_linear_dispatch.py").write_text("# synthetic reviewed script\n")
    environment = {"PILOT_INTAKE_TOKEN": "synthetic-local-token-" + "t" * 40,
                   "LINEAR_READ_API_KEY": "synthetic-read-only-key",
                   "LOCAL_DEMO_ROUTES": "false", "WORKFLOW_PERSISTENCE": "postgres",
                   **{name: f"00000000-0000-0000-0000-{index:012d}"
                      for index, name in enumerate(checker.BINDINGS.values(), 1)}}
    environment["PILOT_LINEAR_PROJECT_ID"] = "none"
    services = {"intake": {"environment": environment},
                "db": {"environment": {"POSTGRES_PASSWORD": "a" * 64, "APP_DB_PASSWORD": "b" * 64}},
                "windmill-init": {"environment": {"WINDMILL_DB_PASSWORD": "c" * 64}}}
    states = [{"Service": name, "State": "running", "Health": "healthy"} for name in checker.RUNNING]
    states += [{"Service": name, "State": "exited", "ExitCode": 0} for name in checker.INITIALIZERS]
    data = {"workspace": True, "folder": True, "script": True,
            "variables": [{"path": "f/platform/" + name, "secret": secret,
                           "present": True, "matches": None if secret else True}
                          for name, secret in checker.VARIABLES.items()]}
    fixture = {"services": services, "states": states, "data": data, "calls": [],
               "applied": True, "health": {"database_healthy": True, "workers_alive": 1}}

    def command(args, *, input=None):
        fixture["calls"].append((args, input))
        if "config" in args:
            value = json.dumps({"services": fixture["services"]})
        elif "info" in args:
            value = "test-version"
        elif "ps" in args:
            value = "\n".join(json.dumps(row) for row in fixture["states"])
        elif "psql" in args:
            value = json.dumps(fixture["data"])
        elif "curl" in args:
            value = json.dumps(fixture["health"])
        else:
            assert "python" in args
            value = json.dumps(fixture["applied"])
        return CompletedProcess(args, 0, value, "")

    monkeypatch.setattr(checker, "command", command)
    return fixture


def test_ready_preflight_is_read_only_and_redacts_values(ready, capsys):
    assert checker.main([]) == 0
    output = capsys.readouterr().out
    assert "Preflight PASSED (local readiness only" in output
    assert "[MANUAL]" in output
    environment = ready["services"]["intake"]["environment"]
    for name in ("PILOT_INTAKE_TOKEN", "LINEAR_READ_API_KEY"):
        assert environment[name] not in output
        assert all(environment[name] not in str(args) for args, _ in ready["calls"])
    sql = next(input for args, input in ready["calls"] if "psql" in args)
    assert "BEGIN READ ONLY;" in sql and "COMMIT;" in sql
    assert "'secret', is_secret" in sql
    assert "decrypt" not in sql.lower()
    assert all(not {"up", "run", "start", "create", "deploy"}.intersection(args)
               for args, _ in ready["calls"])


def test_reports_all_missing_linear_configuration(ready, capsys):
    environment = ready["services"]["intake"]["environment"]
    environment["LINEAR_READ_API_KEY"] = ""
    for name in checker.BINDINGS.values():
        environment[name] = ""
    assert checker.main([]) == 1
    output = capsys.readouterr().out
    for name in ("LINEAR_READ_API_KEY", *checker.BINDINGS.values()):
        assert "[FAIL] " + name in output


def test_checks_unhealthy_services_and_failed_initializers(ready, capsys):
    ready["states"][0]["Health"] = "unhealthy"
    ready["states"][-1]["ExitCode"] = 1
    assert checker.main([]) == 1
    output = capsys.readouterr().out
    assert "[FAIL] Service db" in output
    assert "[FAIL] Initializer windmill-init" in output


@pytest.mark.parametrize("field", ["workspace", "folder", "script"])
def test_missing_ui_prerequisite_is_not_ready(ready, capsys, field):
    ready["data"][field] = False
    assert checker.main([]) == 1
    label = {"workspace": "Windmill workspace sdlc-pilot", "folder": "Windmill folder platform",
             "script": checker.SCRIPT_PATH}[field]
    assert "[FAIL] " + label in capsys.readouterr().out


@pytest.mark.parametrize("change", ["absent", "empty", "wrong_secret_flag", "binding_mismatch"])
def test_detects_variable_configuration_errors(ready, capsys, change):
    row = ready["data"]["variables"][-1]
    if change == "absent":
        ready["data"]["variables"].pop()
    elif change == "empty":
        row["present"] = False
    elif change == "wrong_secret_flag":
        row["secret"] = True
    else:
        row["matches"] = False
    assert checker.main([]) == 1
    assert "[FAIL] f/platform/linear_project_id" in capsys.readouterr().out


def test_detects_stale_running_intake(ready, capsys):
    ready["applied"] = False
    assert checker.main([]) == 1
    assert "[FAIL] Running intake configuration" in capsys.readouterr().out


def test_process_health_does_not_replace_worker_heartbeat(ready, capsys):
    ready["health"]["workers_alive"] = 0
    assert checker.main([]) == 1
    assert "[FAIL] Windmill database and worker heartbeat" in capsys.readouterr().out


def test_missing_docker_cli_fails_without_subprocess(ready, monkeypatch, capsys):
    monkeypatch.setattr(checker.shutil, "which", lambda _: None)
    assert checker.main([]) == 1
    assert not ready["calls"]
    assert "[FAIL] Docker CLI" in capsys.readouterr().out


def test_invalid_compose_configuration_is_redacted(ready, monkeypatch, capsys):
    monkeypatch.setattr(checker, "command", lambda *a, **k: None)
    assert checker.main([]) == 1
    assert "[FAIL] Compose configuration" in capsys.readouterr().out


def test_metadata_failure_is_redacted(ready, monkeypatch, capsys):
    def failed(*args):
        raise ValueError("synthetic-sensitive-diagnostic")

    monkeypatch.setattr(checker, "metadata", failed)
    assert checker.main([]) == 1
    assert "synthetic-sensitive-diagnostic" not in capsys.readouterr().out


def test_alternate_workspace_is_passed_as_quoted_psql_variable(ready):
    assert checker.main(["--workspace", "existing-workspace"]) == 0
    args = next(args for args, _ in ready["calls"] if "psql" in args)
    assert "workspace=existing-workspace" in args


def test_compose_json_array_and_ndjson_formats():
    rows = [{"Service": "db"}, {"Service": "api"}]
    assert checker.records(json.dumps(rows)) == rows
    assert checker.records("\n".join(json.dumps(row) for row in rows)) == rows


@pytest.mark.parametrize("failure", [OSError("synthetic-sensitive-error"),
                                    TimeoutExpired("test", 1, output="synthetic-sensitive-error")])
def test_child_failures_do_not_print_diagnostics(monkeypatch, capsys, failure):
    def failed(*args, **kwargs):
        assert kwargs["capture_output"] and kwargs["timeout"] == 15
        assert not kwargs.get("shell")
        raise failure

    monkeypatch.setattr(checker.subprocess, "run", failed)
    assert checker.command(["docker", "info"]) is None
    assert not capsys.readouterr().out
