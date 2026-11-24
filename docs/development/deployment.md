# Local Docker Compose deployment

## Scope and prerequisites

This is a local A0/A1 demonstration. Starting containers is not authorization to execute Codex, modify GitHub/Linear, deploy a project or expose the API publicly. The selected architecture and responsibilities are described in [architecture](../platform/architecture.md); minimum controls are in [security](../platform/security.md).

Use Docker Engine with Compose v2 or later, Python 3 for the acceptance harness, and registry/package access for the initial build. Reserve approximately 4 CPU cores, 8 GiB available RAM and 20 GiB free disk for this one-worker development stack, image downloads, builds and retained test volumes. These are planning allowances, not benchmarked minimums. Windmill's [self-host guidance](https://www.windmill.dev/docs/advanced/self_host) suggests 1 CPU and 1–2 GiB per worker; this Compose file caps its worker at 1 CPU/2 GiB. The API/intake services each have a 512 MiB cap and the server a 1 GiB cap. Database and builds need additional capacity.

In WSL2, use a Linux distribution such as Ubuntu and keep the repository in its Linux filesystem, not a Windows-mounted project directory. Either enable that distribution's Docker Desktop WSL integration or use its own supported Docker Engine installation; verify the selected context with `docker context show`, `docker version` and `docker compose version`. Avoid mixing daemons/contexts. Ensure sufficient Docker/WSL memory and disk allocation. Use LF line endings for shell scripts. Ports are reached from the host through localhost; `127.0.0.1` inside a container refers to that container. Never change the host bind to `0.0.0.0` to troubleshoot WSL access.

## Configuration reference

Use [the quickstart](../quickstart.md) as the single onboarding procedure. It owns the editable `.env` table, Linear key creation, Windmill workspace/secret setup, script import and daily startup. This document retains deployment internals and operational limits.

Compose supplies `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, bounded `DB_CONNECT_TIMEOUT` and `WORKFLOW_PERSISTENCE=postgres`. Only the private intake listener receives `PILOT_INTAKE_TOKEN`, `LINEAR_READ_API_KEY` and the four `PILOT_LINEAR_*` identity settings; it disables legacy routes with `LOCAL_DEMO_ROUTES=false`. Python does not automatically load `.env`. Environment values remain inspectable by trusted Docker administrators; this is not a production secret manager.

[The read-only preflight](../../scripts/setup_check.py) captures resolved Compose configuration in memory and checks service health, applied intake configuration, worker heartbeat and Windmill metadata. Database reads use explicit read-only transactions; secrets are not decrypted or returned. It cannot verify actual Linear permissions or human authorization. It does not change configuration or submit a workflow. The pinned Windmill schema is its metadata compatibility boundary.

## Services, networks and persistence

| Service | Responsibility and dependencies |
| --- | --- |
| `db` | Existing pinned PostgreSQL 17/pgvector image and `postgres_data` volume; `pg_isready` health check; no host port |
| `migrate` | Original additive platform/checkpointer setup plus immutable intake registry; separate admin credential; waits for DB |
| `windmill-init` | Repeatable additive Windmill database/role setup on the same cluster; separate admin credential; waits for DB |
| `api` | Same existing application, loopback compatibility port; waits for migration; HTTP DB/vector health check |
| `intake` | Same application/image, private integration listener; legacy/docs routes disabled; waits for migration; HTTP DB/vector health check |
| `windmill-server` | Pinned Community image in upstream `MODE=server`; private DB URL; loopback UI port; waits for Windmill init; `/api/health/status` probe |
| `windmill-worker` | Same pinned image in `MODE=worker`, default group; waits for server/intake health; process-liveness probe |
| `tests` | Opt-in test profile; synthetic approval fixtures receive admin credentials only inside this test container |

Worker liveness alone does not prove queue processing. The acceptance harness additionally verifies Windmill's active-worker report and executes actual worker jobs. Server health may be degraded while the first worker starts. Dependencies order startup, not automatic recovery from later crashes; there is no production supervisor or availability guarantee.

The internal `database` network connects only platform-facing DB clients. The separate internal `windmill_database` network connects Windmill to the same DB container. The internal `control` network connects the worker to private intake. Separate `local_api`/`windmill_ui` bridges enable loopback publishing. `egress` permits intake/worker outbound requests; there is no domain-based egress filter. The worker cannot resolve/reach the `api` service through a shared Docker network.

The existing platform database and `windmill` database have different runtime credentials. `windmill_login` owns its database and inherits the upstream-required `windmill_admin`/`windmill_user` roles, without SUPERUSER/CREATEDB/CREATEROLE. Public CONNECT is revoked on both application databases; explicit grants permit only their respective runtime login. This is database separation, not separate physical clusters or tenant RLS.

The original entrypoint script runs only on a fresh volume and still initializes vector and `sdlc_app`. Both one-shot migrations run additively on retained volumes. Windmill performs its own database schema migrations. Existing passwords are not changed by these scripts. Changing `.env` does not rotate an existing login. Diagnose mismatches rather than deleting a volume.

`postgres_data` retains platform checkpoints, identities, approvals, intake keys and Windmill queue/configuration/encrypted secrets. `windmill_cache` retains dependency cache; `windmill_logs` retains operational logs. Never place real issue descriptions, production secrets or customer data in tests. Ordinary `docker compose stop` or `docker compose down` preserves volumes. Volume deletion and destructive database changes require separate explicit authorization.

No container mounts the host Docker socket. No AI execution container or Codex runner is provisioned. The worker runs trusted scripts with namespace sandboxing disabled, no privileged mode and no host source mount. It must not execute untrusted/model-authored code. API restrictions and Docker networks do not turn Windmill into a hardened agent sandbox.

## Repeatable validation

For normal-stack PostgreSQL/regression tests after startup:

```bash
docker compose --profile test run --build --rm tests
```

This adds synthetic runs/checkpoints/approval records and retains them. Use an isolated test project/volume; the separate admin password exists only for fixtures. Original connectivity tests remain read-only.

For isolated end-to-end local acceptance:

```bash
python3 scripts/verify_red6.py
```

The harness generates a new project name, private temporary env file, distinct synthetic secrets and loopback ports. It builds/starts the stack with [compose.integration.yaml](../../compose.integration.yaml), reruns both initializers, runs tests, creates a local synthetic Windmill workspace/secret variables, and submits the real connector as a worker preview. Only Linear transport is simulated; FastAPI HTTP, authentication, database, graph and interrupts are real. It repeats the job, recreates DB/API/intake/server/worker containers with retained volumes, compares exact pending checkpoint/state and repeats the job again. It removes its containers/networks in `finally` and retains volumes/env for inspection. This also frees Docker subnet allocations between runs.

The overlay builds intake from the test stage and starts a test-only response substitution. Never apply it to an existing development stack or actual credentials. Normal runtime images omit tests and have no mock-Linear configuration switch. A passed harness is not evidence of real Linear API access, user identity validation, independent approval issuance, arbitrary crash recovery or production readiness.

The harness prints its project/env path and safe identifiers. To inspect that project, use its printed `--env-file` and `-p` values plus `-f compose.yaml -f compose.integration.yaml`. Do not publish job logs without reviewing/redacting them. No volume-removal command is part of the harness.

## Upgrade, rollback and troubleshooting

Image digests and Python constraint versions are pinned. Review changes and repeat acceptance before upgrading. Windmill application migrations may have their own rollback constraints; do not downgrade its binary against upgraded state without upstream compatibility review. Platform schema changes in RED-6 are additive, and the old draft graph version is preserved.

To stop locally, run `docker compose stop`. To roll back platform code, stop new listeners/worker and run the prior compatible API while keeping all schemas, roles and volumes. Do not treat deleting Windmill data or restoring only one database as a safe cluster rollback. Backups/restores, credential rotation and production migrations need a separately reviewed procedure.

- Missing secrets: fill all new fields and use `config --quiet`; never print resolved secrets.
- API or DB unavailable: inspect service health and bounded local logs, then verify retained-volume credentials and migration completion.
- Intake 401: token absent, too short or incorrect. Intake 403: pilot contract or verified Linear identity mismatch. Intake 422: schema invalid. Intake 409: conflicting event. Intake 503: configuration, Linear, DB or incomplete checkpoint unavailable. None authorize bypassing checks.
- Worker jobs fail: inspect the private job in the local UI, validate folder-variable permissions, package access and connectivity to `http://intake:8000`; do not expose `/draft` or enable privileged mode.
- Port conflict: change only `API_PORT`/`WINDMILL_PORT`; keep loopback binds.
- Docker unavailable: Python preview/unit tests remain available. Report missing Docker checks as blocked, never passed.

See [validation evidence](red6-validation.md) for actual executed checks and remaining gates.
