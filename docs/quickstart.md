# Quickstart: local Docker stack and manual RED-5 dry-run

Follow this guide once to configure the local stack, a read-only Linear key and Windmill. Afterward, use [Daily startup](#daily-startup). Commands run from the repository directory containing `compose.yaml`. No Python virtual environment is needed for the stack or preflight.

Success means a manual Windmill run returns `awaiting_human_review` with a persisted LangGraph checkpoint. It does not execute Codex, change the website repository, write to Linear/GitHub, approve work or deploy production services. Keep this stack on localhost.

## First-time setup

### 1. Prepare Docker and WSL2

- **Windows:** if Ubuntu is not installed, run the following once in an administrator PowerShell window, restart if prompted, then open Ubuntu and create your Linux user:

  ```powershell
  wsl --install -d Ubuntu
  ```

  Install Docker Desktop for Windows using [Docker's WSL2 setup](https://docs.docker.com/desktop/features/wsl/). In Docker Desktop, enable **Settings > General > Use the WSL 2 based engine** and the Ubuntu distribution under **Settings > Resources > WSL Integration**. Run the remaining commands inside Ubuntu. Skip installation when your existing WSL2/Docker environment already works.
- **Linux:** install Docker Engine and the Compose plugin, or use an existing working local Docker installation. Use Compose v2 or later.
- Keep the checkout in the Linux filesystem, such as `~/www/personal/agentic-sdlc-starter`, rather than `/mnt/c/...`. Install Python 3 if unavailable. Allow roughly 4 CPUs, 8 GiB RAM and 20 GiB free disk for development; these are planning allowances, not measured minimums.

Verify all three commands work, including Docker's **Server** section:

```bash
docker version
docker compose version
python3 --version
```

If Docker reports permission denied or cannot connect, fix Docker Desktop integration/daemon access before continuing. Do not change port bindings or mount a Docker socket into a container.

### 2. Configure the local `.env` file

```bash
cp -n .env.example .env
chmod 600 .env
```

Open `.env` in your local editor. `cp -n` preserves an existing file: add missing settings manually instead of replacing it. Use a password manager to generate four independent local secrets. Use 64 random hexadecimal characters (`0–9`, `a–f`) for each to avoid Compose/URL escaping problems. Do not paste secrets into chat, source control, job arguments or logs.

| `.env` setting | Value to enter / source |
| --- | --- |
| `POSTGRES_DB` | Keep `agentic_sdlc`, or preserve your existing database name |
| `POSTGRES_PASSWORD` | First local secret; preserve the current value on an existing volume |
| `DB_PASSWORD` | Second, different local secret; preserve it on an existing volume |
| `WINDMILL_DB_PASSWORD` | Third, different local secret; hexadecimal is URL-safe; preserve it if already initialized |
| `PILOT_INTAKE_TOKEN` | Fourth local secret, at least 32 characters; also copied manually into Windmill below |
| `API_PORT` | Keep `8000` unless occupied |
| `WINDMILL_PORT` | Keep `8001` unless occupied |
| `LINEAR_READ_API_KEY` | Read-only development key created in step 3; never a production or QMO key |
| `PILOT_LINEAR_WORKSPACE_ID` | `03c2cfb9-397c-44ae-94c8-21c0d5600749` — Redeeming Light |
| `PILOT_LINEAR_TEAM_ID` | `892527f6-5f90-4151-8f86-806023d2185e` — team `RED` |
| `PILOT_LINEAR_ISSUE_UUID` | `db242cb9-156b-4349-8dcc-3e889e110f8e` — issue `RED-5` |
| `PILOT_LINEAR_PROJECT_ID` | Literal `none` — requires the issue to have **no Linear project assignment** |

The identity values above were verified on 2026-11-23. Confirm the workspace, RED team and [RED-5](https://linear.app/redeeming-light/issue/RED-5/build-astro-frontend-foundation-agent-delivered-qa-gated) with the project owner before live use. If its assignment changed, stop and have the exact trusted binding reviewed; do not broaden access or substitute QMO values. `none` is not a wildcard. The platform project is `redeeming-light`; its fixed repository allowlist is `jithutj/redeeminglight`.

Changing a password in `.env` does not rotate a login in a retained database. Never delete/reset volumes to resolve a credential mismatch. Leave Linear fields blank only if starting infrastructure before you have the key; preflight will correctly report the pilot as incomplete.

### 3. Create the read-only Linear credential manually

1. Switch to the **Redeeming Light** workspace in Linear.
2. Open **Settings > Account > Security & Access**, find personal API keys and create a key named, for example, `Local SDLC RED-5 read-only`.
3. Grant **Read** only and restrict team access to **RED**. Do not grant Write, Admin, Create issues or Create comments. If key creation is disabled, ask the workspace administrator for a scoped development key instead of broadening permissions. See [Linear's key-permission documentation](https://linear.app/docs/api-and-webhooks).
4. Store the key in your password manager and paste it into `.env` as `LINEAR_READ_API_KEY`. Use the raw personal API key, without an added `Bearer ` prefix. The same read-only key can be used by the API and the local connector; no write permission is needed.

No command in this guide creates a credential for you. The preflight does not authenticate to Linear or verify key scopes; the first manual run validates live access and identity.

### 4. Start the stack

```bash
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps --all
```

Expected: `db`, `api`, `intake`, `windmill-server` and `windmill-worker` are running/healthy. `migrate` and `windmill-init` finish with exit code `0`; they should not remain running. Initial image downloads and dependency installation can take several minutes.

The API is at `http://127.0.0.1:8000`; Windmill is at `http://127.0.0.1:8001`. If you changed either port in `.env`, use that host port. The connector's private URL stays `http://intake:8000/v1/intake`; do not replace it with localhost or expose it publicly.

### 5. Create the Windmill workspace and all six variables

1. Open `http://127.0.0.1:8001`. On a fresh instance, sign in with the upstream bootstrap account `admin@windmill.dev` / `changeme`, then replace that account/password through the setup UI **before adding integration secrets**. Existing instances should use their existing operator account. See [upstream first-login guidance](https://www.windmill.dev/docs/advanced/self_host#first-time-login).
2. Create a Windmill workspace with ID **`sdlc-pilot`** and display name **SDLC pilot**. Keep automatic username creation; no explicit username override is needed. This local workspace ID is different from the Linear workspace UUID in `.env`. If using an existing workspace, select it and use its ID with `--workspace` in step 7.
3. In that workspace, create folder **`platform`** from the **New > Folder** menu. Keep ownership/access restricted to the trusted connector operator. Do not enable public access or grant unrelated projects access.
4. Open Windmill's **Variables** page and create the following six variables in the `platform` folder. If the UI splits folder and name, select `platform` and enter the final name; verify the resulting full path. These are **variables**, not resource objects. See [Windmill variables and secrets](https://www.windmill.dev/docs/core_concepts/variables_and_secrets) for the Secret setting.

| Exact Windmill variable path | Secret? | Source of value | Purpose |
| --- | --- | --- | --- |
| `f/platform/pilot_token` | **Yes** | Exact `PILOT_INTAKE_TOKEN` from your private `.env` | Authenticate the connector to private FastAPI intake |
| `f/platform/linear_read_key` | **Yes** | Read-only RED-scoped key from step 3; normally the same value as `LINEAR_READ_API_KEY` | Read Linear issue identity without write permission |
| `f/platform/workspace_id` | **No** | Exact `PILOT_LINEAR_WORKSPACE_ID` from `.env` | Reject another Linear organization/workspace |
| `f/platform/team_id` | **No** | Exact `PILOT_LINEAR_TEAM_ID` from `.env` | Bind lookup to the approved team UUID and `RED` key |
| `f/platform/issue_uuid` | **No** | Exact `PILOT_LINEAR_ISSUE_UUID` from `.env` | Bind the stable issue UUID as well as identifier `RED-5` |
| `f/platform/linear_project_id` | **No** | Exact `PILOT_LINEAR_PROJECT_ID` from `.env`, initially literal `none` | Require the approved project assignment or explicitly unassigned state |

Copy plain text values without surrounding quotes or spaces. Only the first two variables use **Secret = on**. Save all six in the selected workspace. A green service health check does not create these variables for you.

### 6. Import the reviewed Python connector

1. In the same Windmill workspace, choose **New > Script**, select **Python**, and set its full path to **`f/platform/red5_linear_dispatch`**.
2. Open the repository file [windmill/red5_linear_dispatch.py](../windmill/red5_linear_dispatch.py) in your local editor. Copy its **entire contents** into the Windmill editor, replacing starter code. No source-code changes are needed. Preserve the first requirements lines declaring `wmill==1.875.0`.
3. Click Windmill's **Deploy** button to save/version this reviewed script **in the local instance**. This UI label does not mean deploying a website or production service. Wait for dependency resolution to finish and preserve the generated lock.
4. Leave schedules, public webhooks and other triggers disabled. The generated form should expose only `issue_id`, default `RED-5`. Do not add token, URL, command or approval arguments. Keep folder access restricted to the operator.

Windmill's [Python script guide](https://www.windmill.dev/docs/getting_started/scripts_quickstart/python) describes its editor/save/run UI. Do not import a simulated test script or use `compose.integration.yaml` for this live development setup.

### 7. Run the safe preflight

```bash
python3 scripts/setup_check.py
```

For an existing Windmill workspace with a different ID:

```bash
python3 scripts/setup_check.py --workspace YOUR_WORKSPACE_ID
```

The checker reads configuration in memory, service health and Windmill metadata through a read-only database transaction. It verifies all six variable paths/secret flags, non-secret bindings, running intake configuration, a worker heartbeat, and the exact saved Python script/dependency lock. It never displays/decrypts secrets, calls Linear, submits jobs, modifies `.env`, creates UI objects or starts services. It uses your existing local Docker access; no extra Windmill API token is required.

Exit code `0` means local checks passed. Exit code `1` means a prerequisite failed; fix the named item and rerun. A successful run includes these lines (other checks also appear):

```text
[OK] Compose configuration
[OK] Service windmill-worker
[OK] Windmill workspace sdlc-pilot
[OK] f/platform/pilot_token
[OK] f/platform/linear_read_key
[OK] f/platform/workspace_id
[OK] f/platform/team_id
[OK] f/platform/issue_uuid
[OK] f/platform/linear_project_id
[OK] f/platform/red5_linear_dispatch
[MANUAL] Verify Linear read-only/team scopes, Windmill folder access, and both secret values in the UI.
Preflight PASSED (local readiness only; live Linear handoff remains unverified).
```

Before running the pilot, manually confirm the token matches `.env`, the Linear credential is read-only/RED-scoped, and the script operator can read the six variables. Preflight checks presence/flags, not decrypted secret equality, credential validity or user permissions. It cannot certify isolation or grant approval.

### 8. Run RED-5 manually and inspect the result

Open **`f/platform/red5_linear_dispatch`** in Windmill, set `issue_id` to **`RED-5`**, and click **Run** once. Do not put secrets in the input form. Inspect its result in **Runs**. Expected shape:

```json
{
  "run_id": "<server-generated UUID>",
  "thread_id": "<server-generated UUID>",
  "status": "awaiting_human_review",
  "codex_executed": false,
  "git_write_performed": false
}
```

The script performs read-only Linear lookup; FastAPI independently revalidates identity and persists the deterministic planning draft through LangGraph. Run it again unchanged: expect the same run/thread/status. This is an idempotent retry, not a new draft or human approval. Do not reset the event to force a fresh run. Keep the run IDs as evidence and do not share unredacted job logs. Only this successful live manual request proves your configured Linear handoff; the earlier Docker acceptance used simulated Linear responses.

## Daily startup

Do not recreate credentials, variables or scripts each day. From the same checkout and Docker context:

```bash
docker compose up -d --wait
python3 scripts/setup_check.py
```

Use `--workspace YOUR_WORKSPACE_ID` if applicable. Then open Windmill and run the existing script manually with `RED-5` when needed. Stop locally with `docker compose stop`; data remains in named volumes.

After deliberately editing `.env` integration settings, apply them with `docker compose up -d --wait intake` and update the corresponding Windmill variables manually. After reviewed application changes, use `docker compose up --build -d --wait`. None of these steps rotate an existing database password automatically. Never remove database volumes as a daily-startup or troubleshooting step.

## Common problems

| Symptom | Action |
| --- | --- |
| Compose says a required variable is missing | Open the existing `.env` and fill that row from step 2. Do not overwrite it with `.env.example`. Run `docker compose config --quiet`; never share resolved configuration. |
| Docker unavailable, permission denied or service checks fail | Start the intended local daemon/WSL integration. Run `docker compose ps --all`; inspect only the failing service's local logs and redact before sharing. Do not broaden bindings or privileges. |
| Port 8000 or 8001 already in use | Change only `API_PORT`/`WINDMILL_PORT` in `.env`, restart the affected service and use the new localhost URL. The private connector URL does not change. |
| DB authentication fails on a retained volume | Restore the matching existing local credentials or arrange a reviewed rotation. Editing `.env` does not change the database login. Never reset/delete the volume. |
| Distinct database password check fails | Three independent credentials are required. If a login already exists with a duplicated password, arrange a reviewed database credential rotation and matching configuration update; do not silently replace `.env` values. |
| Missing workspace, folder, variable, wrong Secret flag or mismatched identity | Select the intended workspace and correct step 5. Run preflight with that workspace ID. Do not change the platform allowlist. |
| Running intake configuration does not match `.env` | Run `docker compose up -d --wait intake` after your intentional edits. |
| Script missing, changed or dependency lock unavailable | Repeat step 6 with the exact repository file and wait for dependency resolution. Review failures locally; do not add arbitrary packages or remove the requirements header. |
| `ScopeDenied` / HTTP 403 | Confirm Redeeming Light/RED/RED-5 and the reviewed project assignment. Reject QMO and other scopes; obtain trusted configuration review rather than relaxing checks. |
| `IntegrationUnavailable`, HTTP 401/503 or missing variable access | Compare both token values manually; verify read-only Linear key, operator folder permissions, all six paths, running intake configuration and worker outbound connectivity. Do not expose private intake. |
| HTTP 409 | A different task/configuration conflicts with the persisted pilot event. Retry only the unchanged request or request operator diagnosis; do not overwrite/replay approval state. |
| A repeated run returns the previous IDs | Expected deduplication. `awaiting_human_review` does not permit Codex execution or self-approval. |

Architecture, isolation limitations, database privileges, upgrades and deeper tests remain in [architecture](platform/architecture.md), [security](platform/security.md), [deployment](development/deployment.md), [persistence](platform/workflow-persistence.md) and [validation evidence](development/red6-validation.md). The [project record](projects/redeeming-light/pilot.md) retains pilot history and scope. This guide is the single source for first-time/daily onboarding steps.
