# Platform architecture

## Confirmed implementation

This repository is a local demonstration, not an autonomous coding platform.

| Source | Confirmed behavior |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | Python >=3.11; FastAPI, Uvicorn, Pydantic, LangGraph and Psycopg 3 (binary distribution); pytest and httpx for development. Python dependencies use version ranges. |
| [app/main.py](../../app/main.py), [app/database.py](../../app/database.py) | Unauthenticated `GET /health` reports local-demo mode and external writes disabled. `POST /draft` validates a task and invokes the compiled graph synchronously. `GET /db-health` checks connectivity and the vector extension, returning 200 or a redacted 503. Connections use environment configuration, bounded connection/statement timeouts and read-only transactions; there is no startup database dependency in Python. |
| [app/models.py](../../app/models.py) | Task carries nonempty project/run IDs and objective, plus a level defaulting to A0. Action and Approval are data models. The draft route does not use the task's level to authorize execution. |
| [app/workflow.py](../../app/workflow.py) | `START → draft → END`; the node prefixes the objective with `DRAFT ONLY:` and returns `awaiting_human_review`. State has project/run IDs, objective, draft and status. No model calls, tools, checkpointer or persistence are configured. The status is a returned string, not an approval interrupt. |
| [app/policy.py](../../app/policy.py) | Standalone `authorize()` checks project/run scope, an audit-availability flag and capability/level rules. Reads are allowed at all defined levels; local drafts at A1–A3; PR/issue writes at A2–A3 require matching, unexpired caller-supplied approval data. Other capabilities are denied. No API route or external tool adapter invokes it. |
| [Dockerfile](../../Dockerfile) | Python 3.12 slim runtime and test stages, UID/GID 65532. Default Uvicorn bind is loopback; Compose overrides the container bind for port forwarding. |
| [compose.yaml](../../compose.yaml) | API published at host `127.0.0.1:8000`; existing read-only filesystem, capability, privilege and resource restrictions retained. PostgreSQL 17/pgvector 0.8.7 image pinned by digest, internal-only database network, no database host port, readiness check and persistent `postgres_data` volume. Optional test service runs inside the database network. This is not a complete execution sandbox. |
| [docker/postgres/001-init.sh](../../docker/postgres/001-init.sh) | First-run initialization enables vector and creates the restricted `sdlc_app` login; API receives no bootstrap-admin password. No application schema is created. |
| [tests/test_api.py](../../tests/test_api.py), [tests/test_policy.py](../../tests/test_policy.py) | API smoke checks and selected policy checks for reads, scope mismatch, A0 writes, approval matching/expiry, unavailable audit and production denial. |

The database foundation has opt-in read-only [integration tests](../../tests/test_database_integration.py) and mocked [connectivity tests](../../tests/test_database.py). There is no application database persistence, authenticated approval service, audit store, LLM provider integration, OpenHands runner, RAG or external service integration. Project/run IDs are input fields and policy comparison values; they do not establish tenant isolation. Policy capability names do not imply implemented GitHub or issue-tracker access.

## Future plans — not implemented

The [README roadmap](../../README.md) proposes authenticated APIs, a project registry, durable Postgres state, append-only audit and enforcement on every tool adapter; server-issued one-time human approvals bound to exact resources and artifact digests; durable LangGraph checkpoints and interrupt/resume; isolated OpenHands execution; project-scoped RAG; and staged read-only integrations followed by separately authorized narrow writes.

These require separate tasks, designs and security review. Phase 1A supplies database connectivity only, without workflow persistence or RAG. Provider independence currently means shared coding-agent instructions; it does not imply an implemented model-provider abstraction. See [security guardrails](security.md) before extending trust boundaries.
