# Agentic SDLC Platform — Local Starter v0.1

**Scope:** Local A0/A1 platform using Windmill Community, FastAPI, LangGraph OSS and PostgreSQL/pgvector. RED-6 adds authenticated, project-bound intake and a manual read-only Linear connector to the existing durable draft/review workflow. Codex CLI execution, RAG, GitHub integration and production isolation remain planned. No HTTP approval/resume endpoint exists. See [validation evidence](docs/development/red6-validation.md) for tested versus simulated behavior.

**Start here: [Docker/WSL2 quickstart and manual RED-5 setup](docs/quickstart.md).** It covers first-time setup, Linear credentials, all six Windmill variables, script import, safe preflight, expected output and daily startup.

## Local runtime

Use the quickstart for Docker onboarding. Optional Python-only development and its request-local memory preview are documented in [development workflow](docs/development/workflow.md). The preview is not the persistent Windmill pilot. Compose requires PostgreSQL and never silently falls back to memory.

The compatibility API publishes only on host loopback, and Windmill reaches a separate private intake listener with legacy routes disabled. PostgreSQL has no host port. The existing PostgreSQL/pgvector volume, migrations and graph/review gates are retained. Advanced network, configuration and resource details remain in [deployment](docs/development/deployment.md).

## Initialization and configuration

On an **empty** named volume, the Postgres entrypoint creates the database and runs [001-init.sh](docker/postgres/001-init.sh). It enables `vector` and creates the non-superuser `sdlc_app` login without schema-create privileges. A separate one-shot `migrate` service uses the bootstrap-admin password to initialize the private workflow schema and checkpoint tables. The API receives only runtime credentials and starts after successful migration. Existing Phase 1A volumes are upgraded additively; do not reset them. The `windmill-init` service adds a separate `windmill` database and restricted login on the same PostgreSQL cluster, including existing volumes. Windmill owns its queue and operational metadata; it cannot connect to the platform database. Both databases remain in `postgres_data`.

Compose maps `DB_PASSWORD` to the initialization script and the API. The API reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and optional `DB_CONNECT_TIMEOUT` (default 3 seconds, allowed 2–10). `/db-health` opens one read-only connection per probe. Workflows use separate read/write connections and 3-second statement/lock timeouts. These bound individual stages, not a strict whole-request deadline including DNS. There is no pool or ORM yet.

Compose sets `WORKFLOW_PERSISTENCE=postgres`. `/draft` retains its response fields and adds a server-generated `thread_id`. A repeated project/run pair returns 409 without revealing the existing state. The draft now pauses at a real review interrupt. No HTTP state lookup, approval or resume endpoint exists. See [workflow persistence](docs/platform/workflow-persistence.md) for identity mapping, internal resume, permissions and restart verification.

The original entrypoint initialization runs only once; the additive `migrate` and `windmill-init` services are repeatable. Changing `.env` does **not** rotate passwords, rename databases or rerun scripts on an existing volume. Coordinate credential changes with an authorized database administrator; never delete the volume to fix a login failure. A host Python process cannot use Compose DNS name `db` or reach this database through a published port. Use the container workflow for database tests, or explicitly configure a separately managed development database.

## RED-6 intake and RED-5 pilot

Windmill handles manual invocation and read-only Linear lookup. FastAPI authenticates a scoped service token, validates the contract, independently verifies Linear identity, and deduplicates the event in PostgreSQL. LangGraph executes the existing `draft-review-v1` graph and saves a real human-review interrupt. Duplicate intake reads that state; it never resumes or approves it. The objective and planning response are deterministic, not model-generated work.

Configure the trusted workspace/team/issue/project binding and import [the manual script](windmill/red5_linear_dispatch.py) using the [quickstart](docs/quickstart.md). No polling, public webhook or production credential is enabled. The pilot does not complete the website issue.

## Tests and persistence verification

Repeatable Docker acceptance proof with generated synthetic secrets and a new isolated Compose project:

```bash
python3 scripts/verify_red6.py
```

This uses real Windmill jobs, private HTTP, PostgreSQL and LangGraph, but explicitly **simulates Linear responses**. It compares the pending checkpoint before and after database/API/Windmill container recreation, retries the same job, then removes test containers/networks while retaining volumes. It does not prove live Linear integration. Never apply [the simulation overlay](compose.integration.yaml) to an existing or credentialed stack.

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

- **Compose reports a missing password:** populate all three password fields and the separate intake token in your local `.env`. Use `docker compose config --quiet` to validate without printing resolved secrets.
- **Database stays unhealthy:** inspect `docker compose ps` and local `docker compose logs db` for startup, disk or initialization errors. Review/redact logs before sharing. `pg_isready` tests server readiness; `/db-health` additionally checks application authentication and the extension.
- **HTTP 503:** check configuration, existing-volume credentials and initialization. From the database container, inspect `SELECT extversion FROM pg_extension WHERE extname = 'vector';` as the admin. For an existing database missing the extension or role, review and authorize an additive migration; initialization scripts are not a migration system.
- **Port 8000 occupied:** stop the other local API process or set `API_PORT=18000` in `.env` and use that port in requests. The host binding remains loopback-only.
- **Docker unavailable or image pull fails:** unit tests and the original Python demo remain usable; integration tests require a working daemon and registry access. The new driver also requires reinstalling project dependencies.

## Security limitations

- `/draft` remains unauthenticated and MUST stay on localhost. The separate integration listener authenticates one restricted service principal; its token is not a human identity or approval. Only the read-only pilot connector receives explicitly configured development Linear credentials.
- `authorize()` is a testable policy function, **not** wired to external tools. A2 approval objects are caller-supplied; real approvals require independently authenticated human identity, immutable records and one-time consumption.
- Platform routes perform no shell execution, GitHub writes, Linear mutations, Codex invocation or model calls. Windmill can execute operator-authored scripts: run only the reviewed connector, never issue-derived code. This worker is not an AI sandbox.
- Compose persists workflow state and review interrupts. Python-only memory previews are not durable. There is no authenticated approval/resume API.
- Compose isolates the database on an internal network and retains API container restrictions; it is not a full hardened sandbox. Local Docker administrators can inspect container environment credentials.
- Runtime image digests and resolved Python versions are pinned; artifact hashes, vulnerability scanning, credential rotation, rate limiting and production hardening remain separate gates.

## Next implementation gates

1. Extend the narrow service-token pilot to independently authenticated principals, broader project membership, durable audit and enforcement on every future tool adapter. Current SQL credentials are not tenant-isolated.
2. Add an independently authenticated approval issuer and scoped retrieval/resume API. Internal resume already checks one-use server records bound to exact checkpoints/state digests.
3. Extend checkpoint recovery, retention and graph-version migration beyond the current deterministic draft/review workflow.
4. Implement and security-test an isolated Codex CLI runner without host Docker socket, production credentials or unrestricted network. No runner is currently registered or invoked. This supersedes earlier OpenHands guidance.
5. Add project-scoped LangChain RAG and SEC-01..SEC-12 tests.
6. Validate the configured live read-only Linear handoff. GitHub integration and all external writes need separate authorization.

## Documentation

- [Quickstart](docs/quickstart.md): first-time onboarding and daily startup.
- [AGENTS.md](AGENTS.md): shared coding-agent instructions and selective context loading.
- [CLAUDE.md](CLAUDE.md): thin Claude Code adapter to the shared instructions.
- [Local deployment](docs/development/deployment.md): Compose, configuration, resources and WSL2.
- [RED-6 validation and documentation summary](docs/development/red6-validation.md): actual checks, gaps and future source revisions.
- [Windmill decision record](docs/decisions/0001-windmill.md): selection over Activepieces/n8n.
- [Development workflow](docs/development/workflow.md): local development, validation and agent handoffs.
- [Platform architecture](docs/platform/architecture.md): confirmed implementation and clearly separated future plans.
- [Security guardrails](docs/platform/security.md): minimum development boundaries and current limitations.
- [Workflow persistence](docs/platform/workflow-persistence.md): checkpoints, interrupts, internal approval gates, migrations and restart verification.

This repository builds a reusable platform, not the Redeeming Light website. Project-specific documents stay outside default coding-agent context and are loaded only for relevant tasks. Previously named platform/security/project reference documents are not present here; their contents are not assumed by this documentation.
