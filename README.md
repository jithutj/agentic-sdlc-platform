# Agentic SDLC Platform — Local Starter v0.1

**Scope:** Local FastAPI + LangGraph draft demonstration with PostgreSQL/pgvector, durable workflow checkpoints and an internal human-review interrupt/resume foundation (Task 003). **Not a working autonomous coding platform.** No OpenHands, RAG, authenticated approval issuer, external integrations or production-ready isolation are implemented. Approval/resume is not exposed over HTTP.

## Quick start in WSL2 Ubuntu

```bash
unzip agentic-sdlc-starter.zip
cd agentic-sdlc-starter
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/draft -H 'Content-Type: application/json' -d '{"project_id":"demo","run_id":"r1","objective":"Draft an API design"}'
```

The Python-only demo defaults to request-local memory previews: `/health` and `/draft` still work; `/db-health` returns HTTP 503 until configured. Python does not automatically load `.env`. Compose requires PostgreSQL persistence; it never silently falls back to memory.

## Docker database setup

Requires Docker Engine and Docker Compose v2 or later. Stop a host Uvicorn process first if it already occupies port 8000.

1. Copy `.env.example` to `.env` without overwriting an existing configuration, and restrict its permissions:

   ```bash
   cp -n .env.example .env
   chmod 600 .env
   ```

2. In your local editor, set `POSTGRES_PASSWORD` and `DB_PASSWORD` to two different randomly generated, local-only passwords. Blank values intentionally prevent startup. Keep `.env` private and untracked; do not paste it or resolved Compose output into tickets or logs. `POSTGRES_DB` defaults to `agentic_sdlc`.
3. Validate and start:

   ```bash
   docker compose config --quiet
   docker compose up --build -d --wait
   docker compose ps
   curl -i http://127.0.0.1:8000/db-health
   ```

Expect HTTP 200 with `{"status":"ok"}` after initialization. Failures return HTTP 503 with `{"status":"unavailable"}`, without credentials or driver details. `/health` remains a process health check; `/db-health` checks a database query and that the vector extension is enabled.

The database uses `pgvector/pgvector:0.8.7-pg17-bookworm` pinned to an immutable multi-platform digest in [compose.yaml](compose.yaml). PostgreSQL 17 is a [supported major version](https://www.postgresql.org/support/versioning/); see the [upstream pgvector image documentation](https://github.com/pgvector/pgvector#docker). Upgrading requires deliberate tag/digest review.

The API publishes only `127.0.0.1:8000` by default (`API_PORT` changes only the port). Its container listens on `0.0.0.0` to receive traffic through that loopback-only mapping. PostgreSQL has no host port and joins only the internal `database` network; the API joins that network and the default bridge. This replaces the previous host-network setup. Standalone Dockerfile execution still defaults to loopback binding.

## Initialization and configuration

On an **empty** named volume, the Postgres entrypoint creates the database and runs [001-init.sh](docker/postgres/001-init.sh). It enables `vector` and creates the non-superuser `sdlc_app` login without schema-create privileges. A separate one-shot `migrate` service uses the bootstrap-admin password to initialize the private workflow schema and checkpoint tables. The API receives only runtime credentials and starts after successful migration. Existing Phase 1A volumes are upgraded additively; do not reset them.

Compose maps `DB_PASSWORD` to the initialization script and the API. The API reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and optional `DB_CONNECT_TIMEOUT` (default 3 seconds, allowed 2–10). `/db-health` opens one read-only connection per probe. Workflows use separate read/write connections and 3-second statement/lock timeouts. These bound individual stages, not a strict whole-request deadline including DNS. There is no pool or ORM yet.

Compose sets `WORKFLOW_PERSISTENCE=postgres`. `/draft` retains its response fields and adds a server-generated `thread_id`. A repeated project/run pair returns 409 without revealing the existing state. The draft now pauses at a real review interrupt. No HTTP state lookup, approval or resume endpoint exists. See [workflow persistence](docs/platform/workflow-persistence.md) for identity mapping, internal resume, permissions and restart verification.

Initialization runs only once. Changing `.env` does **not** rotate passwords, rename databases or rerun scripts on an existing volume. Coordinate credential changes with an authorized database administrator; never delete the volume to fix a login failure. A host Python process cannot use Compose DNS name `db` or reach this database through a published port. Use the container workflow for database tests, or explicitly configure a separately managed development database.

## Tests and persistence verification

Run unit/regression tests in the activated local virtual environment:

```bash
pytest -q
```

Integration tests are skipped by default. After Docker setup, run all tests, including real pgvector queries, runtime-role privilege checks and rejected-password behavior, inside the private network:

```bash
docker compose --profile test run --build --rm tests
```

`--rm` removes only the finished test container; it does not remove the named database volume. The original connectivity tests remain read-only. New workflow integration tests add synthetic runs/checkpoints/approval fixtures and retain them without deleting data. Use an isolated test database/project. Standalone configuration and opt-in flags are documented in [workflow persistence](docs/platform/workflow-persistence.md).

To verify persistence without adding test data, record the cluster identifier and enabled extension, recreate the database container with its existing volume, and repeat the query. The identifier and extension should remain unchanged:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT system_identifier FROM pg_control_system(); SELECT extversion FROM pg_extension WHERE extname = '\''vector'\'';"'
docker compose up -d --force-recreate --wait db
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT system_identifier FROM pg_control_system(); SELECT extversion FROM pg_extension WHERE extname = '\''vector'\'';"'
curl -i http://127.0.0.1:8000/db-health
```

The `postgres_data` named volume survives container recreation and ordinary `docker compose down`. Require explicit approval before deleting database data or volumes; do not use volume-removal/reset commands as troubleshooting steps.

## Troubleshooting

- **Compose reports a missing password:** populate both blank password fields in your local `.env`. Use `docker compose config --quiet` to validate without printing resolved secrets.
- **Database stays unhealthy:** inspect `docker compose ps` and local `docker compose logs db` for startup, disk or initialization errors. Review/redact logs before sharing. `pg_isready` tests server readiness; `/db-health` additionally checks application authentication and the extension.
- **HTTP 503:** check configuration, existing-volume credentials and initialization. From the database container, inspect `SELECT extversion FROM pg_extension WHERE extname = 'vector';` as the admin. For an existing database missing the extension or role, review and authorize an additive migration; initialization scripts are not a migration system.
- **Port 8000 occupied:** stop the other local API process or set `API_PORT=18000` in `.env` and use that port in requests. The host binding remains loopback-only.
- **Docker unavailable or image pull fails:** unit tests and the original Python demo remain usable; integration tests require a working daemon and registry access. The new driver also requires reinstalling project dependencies.

## Security limitations

- API is unauthenticated and MUST stay on localhost. Never publish it or attach real tokens.
- `authorize()` is a testable policy function, **not** wired to external tools. A2 approval objects are caller-supplied; real approvals require independently authenticated human identity, immutable records and one-time consumption.
- No production or merge operations exist. No arbitrary shell execution, GitHub writes, Linear writes or model calls exist.
- Compose persists workflow state and review interrupts. Python-only memory previews are not durable. There is no authenticated approval/resume API.
- Compose isolates the database on an internal network and retains API container restrictions; it is not a full hardened sandbox. Local Docker administrators can inspect container environment credentials.
- Pin dependencies and scan images before any real deployment.

## Next implementation gates

1. Add authenticated API, trusted project membership, append-only audit and deny-by-default PEP wired to *every* future tool adapter. The current run registry does not establish authenticated tenancy.
2. Add an independently authenticated approval issuer and scoped retrieval/resume API. Internal resume already checks one-use server records bound to exact checkpoints/state digests.
3. Extend checkpoint recovery, retention and graph-version migration beyond the current deterministic draft/review workflow.
4. Add isolated OpenHands execution without host Docker socket, credentials or unrestricted network.
5. Add project-scoped LangChain RAG and SEC-01..SEC-12 tests.
6. Only then connect Linear/GitHub read-only; separately authorize narrow writes.

## Documentation

- [AGENTS.md](AGENTS.md): shared coding-agent instructions and selective context loading.
- [CLAUDE.md](CLAUDE.md): thin Claude Code adapter to the shared instructions.
- [Development workflow](docs/development/workflow.md): local development, validation and agent handoffs.
- [Platform architecture](docs/platform/architecture.md): confirmed implementation and clearly separated future plans.
- [Security guardrails](docs/platform/security.md): minimum development boundaries and current limitations.
- [Workflow persistence](docs/platform/workflow-persistence.md): checkpoints, interrupts, internal approval gates, migrations and restart verification.

This repository builds a reusable platform, not the Redeeming Light website. Project-specific documents stay outside default coding-agent context and are loaded only for relevant tasks. Previously named platform/security/project reference documents are not present here; their contents are not assumed by this documentation.
