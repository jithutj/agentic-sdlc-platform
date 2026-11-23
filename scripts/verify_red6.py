"""Local Docker acceptance proof with simulated Linear and real Windmill jobs.

Creates an isolated Compose project with synthetic secrets. Retains volumes and
removes its containers/networks at completion. Never uses existing projects or real Linear.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main():
    project = "red6-verify-" + uuid4().hex[:10]
    api_port, wm_port = free_port(), free_port()
    values = {key: secrets.token_hex(32) for key in (
        "POSTGRES_PASSWORD", "DB_PASSWORD", "WINDMILL_DB_PASSWORD", "PILOT_INTAKE_TOKEN")}
    values.update(API_PORT=str(api_port), WINDMILL_PORT=str(wm_port), POSTGRES_DB="agentic_sdlc")
    environment = dict(os.environ, **values)
    descriptor, filename = tempfile.mkstemp(prefix=project + "-", suffix=".env")
    with os.fdopen(descriptor, "w") as stream:
        stream.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
    compose = ["docker", "compose", "--env-file", filename, "-p", project,
               "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.integration.yaml")]

    def run(*args, input=None, timeout=600):
        result = subprocess.run([*compose, *args], input=input, text=True,
                                capture_output=True, timeout=timeout, cwd=ROOT, env=environment)
        if result.returncode:
            # Do not emit environment, job logs or raw driver errors.
            raise RuntimeError("Compose step failed: " + " ".join(args[:4]))
        return result.stdout.strip()

    print(json.dumps({"project": project, "env_file": filename, "linear": "simulated"}), flush=True)
    try:
        run("config", "--quiet")
        print("Building and starting isolated Compose stack", flush=True)
        run("up", "--build", "-d", "--wait", "--wait-timeout", "240")
        print("Running PostgreSQL, security and regression tests", flush=True)
        run("run", "--rm", "windmill-init")
        run("run", "--rm", "migrate")
        suite = run("--profile", "test", "run", "--build", "--rm", "tests")
        print(suite.splitlines()[-1], flush=True)

        base = f"http://127.0.0.1:{wm_port}/api"
        bearer = ""

        def api(path, payload=None):
            headers = {"Content-Type": "application/json"}
            if bearer:
                headers["Authorization"] = "Bearer " + bearer
            req = Request(base + path, headers=headers,
                          data=None if payload is None else json.dumps(payload).encode())
            with urlopen(req, timeout=20) as response:
                raw = response.read().decode()
            try:
                return json.loads(raw)
            except ValueError:
                return raw

        health = api("/health/status?force=true")
        assert health["database_healthy"] and health["workers_alive"] >= 1
        bearer = api("/auth/login", {"email": "admin@windmill.dev", "password": "changeme"})
        workspace = "red6-verification"
        api("/workspaces/create", {"id": workspace, "name": "Synthetic RED-6 verification"})
        prefix = "/w/" + workspace
        username = api(prefix + "/users/whoami")["username"]
        api(prefix + "/folders/create", {"name": "platform", "owners": ["u/" + username]})
        scope = {"workspace_id": "00000000-0000-0000-0000-000000000001",
                 "team_id": "00000000-0000-0000-0000-000000000002",
                 "issue_uuid": "00000000-0000-0000-0000-000000000003", "linear_project_id": "none"}
        for name, value in scope.items() | {("pilot_token", values["PILOT_INTAKE_TOKEN"]),
                                           ("linear_read_key", "synthetic-linear-key")}:
            api(prefix + "/variables/create", {"path": "f/platform/" + name, "value": value,
                "is_secret": name in ("pilot_token", "linear_read_key"), "description": "Synthetic test only"})

        # The production script remains unchanged. Only this preview replaces
        # Linear's HTTP response; the handoff uses the real private HTTP network.
        data = {"data": {"organization": {"id": scope["workspace_id"]}, "issue": {
            "id": scope["issue_uuid"], "identifier": "RED-5",
            "team": {"id": scope["team_id"], "key": "RED"}, "project": None}}}
        code = (ROOT / "windmill/red5_linear_dispatch.py").read_text() + "\n" + f"""
_live_post = post_json
def post_json(url, payload, headers):
    if url == LINEAR_URL:
        return {data!r}
    return _live_post(url, payload, headers)
"""

        def job():
            job_id = api(prefix + "/jobs/run/preview", {
                "content": code, "language": "python3", "args": {}, "path": "f/platform/red5_verification"})
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                result = api(prefix + "/jobs_u/get/" + job_id)
                if result.get("type") == "CompletedJob" or "success" in result:
                    if not result.get("success"):
                        raise RuntimeError("Windmill job failed: " + job_id)
                    return result["result"]
                time.sleep(1)
            raise RuntimeError("Windmill job timeout: " + job_id)

        print("Executing real Windmill worker with simulated Linear", flush=True)
        first = job()
        assert first["status"] == "awaiting_human_review"
        assert not first["codex_executed"] and not first["git_write_performed"]
        assert job() == first
        snapshot_code = """
import json, sys
from app.workflow_store import open_workflows
with open_workflows() as workflows:
    identity = ('redeeming-light', sys.argv[1], sys.argv[2])
    print(json.dumps({'state': workflows.read(*identity),
                      'pending': workflows.pending_review(*identity)}, sort_keys=True))
"""

        def snapshot():
            return run("exec", "-T", "api", "python", "-c", snapshot_code,
                       first["run_id"], first["thread_id"])

        before = snapshot()
        print("Recreating database, API and Windmill containers with retained volumes", flush=True)
        run("up", "-d", "--force-recreate", "--no-deps", "--wait", "db")
        run("up", "-d", "--force-recreate", "--no-deps", "--wait", "api", "intake",
            "windmill-server", "windmill-worker")
        assert snapshot() == before
        # Login session, encrypted variables, queue and platform checkpoints all persist.
        assert job() == first
        # The restricted listener must not serve the compatibility draft route.
        run(
            "exec", "-T", "intake", "python", "-c", """
import urllib.request, urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:8000/draft')
except urllib.error.HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError('Compatibility route exposed')
""")
        print(json.dumps({"result": "passed", "linear": "simulated", "windmill_worker": "real",
                          "database": "real", "restart_checkpoint_equal": True,
                          "retry_run_equal": True, "run_id": first["run_id"],
                          "thread_id": first["thread_id"], "suite": suite.splitlines()[-1]}), flush=True)
    finally:
        run("down", timeout=120)
        print("Removed test containers/networks; retained volumes and private env file: " + filename, flush=True)


if __name__ == "__main__":
    main()
