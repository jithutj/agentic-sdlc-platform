"""Read-only local onboarding preflight. Never prints or configures credentials.

Uses the selected Docker context and this repository's normal Compose file.
No HTTP request to Linear, job submission, secret decryption or state write occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
RUNNING = ("db", "api", "intake", "windmill-server", "windmill-worker")
INITIALIZERS = ("migrate", "windmill-init")
BINDINGS = {
    "workspace_id": "PILOT_LINEAR_WORKSPACE_ID",
    "team_id": "PILOT_LINEAR_TEAM_ID",
    "issue_uuid": "PILOT_LINEAR_ISSUE_UUID",
    "linear_project_id": "PILOT_LINEAR_PROJECT_ID",
}
VARIABLES = {"pilot_token": True, "linear_read_key": True,
             **{key: False for key in BINDINGS}}
SCRIPT_PATH = "f/platform/red5_linear_dispatch"


def command(args, *, input=None):
    """Capture all child output; raw errors/configuration may contain secrets."""
    try:
        result = subprocess.run(args, input=input, text=True, capture_output=True,
                                timeout=15, cwd=ROOT)
        return result if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def records(raw):
    """Compose versions return either a JSON array or newline-delimited objects."""
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else [value]
    except ValueError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def metadata(workspace, bindings, script_digest):
    # psql quotes variables as SQL literals; no interpolation into executable SQL.
    # Only non-secret identities/digests appear in argv. No value is returned.
    args = [*COMPOSE, "exec", "-T", "db", "psql", "-X", "-qAt",
            "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "windmill",
            "-v", "workspace=" + workspace, "-v", "script_digest=" + script_digest]
    for key in BINDINGS:
        args += ["-v", key + "=" + bindings.get(key, "")]
    sql = """
BEGIN READ ONLY;
SET LOCAL statement_timeout = '3s';
SELECT json_build_object(
  'workspace', EXISTS(SELECT FROM workspace WHERE id=:'workspace' AND NOT deleted),
  'folder', EXISTS(SELECT FROM folder WHERE workspace_id=:'workspace' AND name='platform'),
  'variables', COALESCE((SELECT json_agg(json_build_object(
      'path', path, 'secret', is_secret,
      'present', value IS NOT NULL AND length(trim(value))>0,
      'matches', CASE WHEN is_secret THEN NULL ELSE CASE path
        WHEN 'f/platform/workspace_id' THEN value=:'workspace_id'
        WHEN 'f/platform/team_id' THEN value=:'team_id'
        WHEN 'f/platform/issue_uuid' THEN value=:'issue_uuid'
        WHEN 'f/platform/linear_project_id' THEN value=:'linear_project_id'
        ELSE NULL END END))
    FROM variable WHERE workspace_id=:'workspace' AND path IN (
      'f/platform/pilot_token','f/platform/linear_read_key','f/platform/workspace_id',
      'f/platform/team_id','f/platform/issue_uuid','f/platform/linear_project_id')), '[]'::json),
  'script', EXISTS(SELECT FROM script WHERE workspace_id=:'workspace'
      AND path='f/platform/red5_linear_dispatch' AND NOT archived AND NOT deleted
      AND language='python3' AND md5(content)=:'script_digest'
      AND lock IS NOT NULL AND length(lock)>0 AND COALESCE(lock_error_logs,'')='')
);
COMMIT;
"""
    result = command(args, input=sql)
    return json.loads(result.stdout) if result else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default="sdlc-pilot", help="Windmill workspace ID (not Linear ID)")
    options = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", options.workspace):
        parser.error("Use a workspace ID containing only letters, digits, underscores or hyphens")
    failures = []

    def check(ok, label, action):
        print(("[OK] " if ok else "[FAIL] ") + label + ("" if ok else ": " + action))
        if not ok:
            failures.append(label)
        return ok

    def finish():
        print("[MANUAL] Verify Linear read-only/team scopes, Windmill folder access, and both secret values in the UI.")
        print("Preflight FAILED; follow docs/quickstart.md." if failures else
              "Preflight PASSED (local readiness only; live Linear handoff remains unverified).")
        return int(bool(failures))

    if not check(shutil.which("docker") is not None, "Docker CLI", "Install/start Docker with Compose v2+"):
        return finish()
    config = command([*COMPOSE, "config", "--format", "json"])
    if not check(config is not None, "Compose configuration", "Fill required .env values; run docker compose config --quiet locally"):
        return finish()
    try:
        services = json.loads(config.stdout)["services"]
        environment = services["intake"]["environment"]
        db = services["db"]["environment"]
        wm = services["windmill-init"]["environment"]
        passwords = (db["POSTGRES_PASSWORD"], db["APP_DB_PASSWORD"], wm["WINDMILL_DB_PASSWORD"])
        check(all(passwords) and len(set(passwords)) == 3, "Distinct database passwords", "Use three distinct local passwords; never rotate retained-volume logins implicitly")
        check(bool(re.fullmatch(r"[A-Za-z0-9_-]+", passwords[2])), "Windmill database URL password", "Use URL-safe hex when first configuring this login")
        check(len(environment.get("PILOT_INTAKE_TOKEN", "")) >= 32, "PILOT_INTAKE_TOKEN", "Set at least 32 random characters manually")
        check(bool(environment.get("LINEAR_READ_API_KEY")), "LINEAR_READ_API_KEY", "Configure a development read-only Linear key manually")
        bindings = {}
        for key, name in BINDINGS.items():
            value = environment.get(name, "")
            valid = value == "none" if key == "linear_project_id" else False
            if not valid:
                try:
                    valid = str(UUID(value)) == value
                except (ValueError, TypeError, AttributeError):
                    valid = False
            check(valid, name, "Copy the verified pilot binding from docs/quickstart.md")
            if valid:
                bindings[key] = value
    except (ValueError, KeyError, TypeError):
        check(False, "Compose configuration shape", "Use this repository's normal compose.yaml")
        return finish()

    env_file = ROOT / ".env"
    if env_file.exists():
        check(env_file.stat().st_mode & 0o077 == 0, "Private .env permissions", "Run chmod 600 .env")
    if not check(command(["docker", "info", "--format", "{{.ServerVersion}}"])
                 is not None, "Docker daemon", "Start Docker or fix access to the selected context"):
        return finish()
    status = command([*COMPOSE, "ps", "--all", "--format", "json"])
    try:
        states = {row["Service"]: row for row in records(status.stdout)} if status else {}
    except (ValueError, KeyError, TypeError):
        states = {}
    for name in RUNNING:
        row = states.get(name, {})
        check(row.get("State") == "running" and row.get("Health") == "healthy",
              "Service " + name, "Run docker compose up -d --wait; inspect this service locally")
    for name in INITIALIZERS:
        row = states.get(name, {})
        check(row.get("State") == "exited" and row.get("ExitCode") == 0,
              "Initializer " + name, "Review local migration logs; preserve database volumes")

    # Compare source configuration with the running listener without emitting values.
    if states.get("intake", {}).get("State") == "running":
        expected = {key: environment.get(key, "") for key in
                    ("PILOT_INTAKE_TOKEN", "LINEAR_READ_API_KEY", *BINDINGS.values(),
                     "LOCAL_DEMO_ROUTES", "WORKFLOW_PERSISTENCE")}
        result = command([*COMPOSE, "exec", "-T", "intake", "python", "-c",
                          "import json,os,sys; expected=json.load(sys.stdin); "
                          "print(json.dumps(all(os.environ.get(k, '') == v for k,v in expected.items())))"],
                         input=json.dumps(expected))
        check(result is not None and result.stdout.strip() == "true", "Running intake configuration",
              "Apply your .env edits with docker compose up -d --wait intake")

    if states.get("windmill-server", {}).get("State") == "running":
        health = command([*COMPOSE, "exec", "-T", "windmill-server", "curl", "--fail", "--silent",
                          "--max-time", "5", "http://127.0.0.1:8000/api/health/status"])
        try:
            data = json.loads(health.stdout) if health else {}
            ready = data.get("database_healthy") is True and data.get("workers_alive", 0) >= 1
        except (ValueError, TypeError, AttributeError):
            ready = False
        check(ready, "Windmill database and worker heartbeat", "Wait for the worker; review local Windmill logs")

    if states.get("db", {}).get("State") != "running":
        check(False, "Windmill workspace metadata", "Start the database before checking UI configuration")
        return finish()
    try:
        script_digest = hashlib.md5((ROOT / "windmill/red5_linear_dispatch.py").read_bytes()).hexdigest()
        data = metadata(options.workspace, bindings, script_digest)
        if data is None:
            raise ValueError
        check(data["workspace"], "Windmill workspace " + options.workspace, "Create/select that workspace in the local UI")
        check(data["folder"], "Windmill folder platform", "Create the restricted platform folder in that workspace")
        variables = {row["path"]: row for row in data["variables"]}
        for name, secret in VARIABLES.items():
            path = "f/platform/" + name
            row = variables.get(path, {})
            valid = row.get("present") is True and row.get("secret") is secret
            if not secret:
                valid = valid and row.get("matches") is True
            check(valid, path, "Create/correct its value and Secret setting using the quickstart table")
        check(data["script"], SCRIPT_PATH, "Save the exact reviewed Python script and resolve its dependency lock in the UI")
    except (OSError, ValueError, KeyError, TypeError):
        check(False, "Windmill workspace metadata", "Check Windmill initialization and local Docker database access")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
