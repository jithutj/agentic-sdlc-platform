# Platform architecture

## Confirmed implementation

This repository is a local demonstration, not an autonomous coding platform.

| Source | Confirmed behavior |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | Python >=3.11; FastAPI, Uvicorn, Pydantic, Psycopg 3, pinned LangGraph 1.2.22 and PostgreSQL checkpointer 3.2.1; pytest and httpx for development. Other Python dependencies use version ranges. |
| [app/main.py](../../app/main.py), [app/database.py](../../app/database.py) | Unauthenticated `GET /health` reports local-demo mode and external writes disabled. `POST /draft` validates a task and invokes the graph synchronously. `GET /db-health` uses a read-only connectivity/vector probe. Workflow connections permit writes and bound statement/lock waits. Responses redact database errors; Python has no startup database dependency. |
| [app/models.py](../../app/models.py) | Task carries nonempty project/run IDs and objective, plus a level defaulting to A0. Action and Approval are data models. The draft route does not use the task's level to authorize execution. |
| [app/workflow.py](../../app/workflow.py), [app/workflow_store.py](../../app/workflow_store.py) | `START → draft → review → END`; deterministic draft followed by a genuine `interrupt()`. Compose uses PostgreSQL checkpoints; Python-only previews use request-local memory. Immutable run registry binds project/run to a server-generated thread UUID, objective digest and graph version. Internal lookup/resume checks identity; resume validates and reserves a one-use approval bound to the pending checkpoint/state digest. No HTTP lookup/approval/resume routes exist. |
| [app/policy.py](../../app/policy.py) | Standalone `authorize()` checks project/run scope, an audit-availability flag and capability/level rules. Reads are allowed at all defined levels; local drafts at A1–A3; PR/issue writes at A2–A3 require matching, unexpired caller-supplied approval data. Other capabilities are denied. No API route or external tool adapter invokes it. |
| [Dockerfile](../../Dockerfile) | Python 3.12 slim runtime and test stages, UID/GID 65532. Default Uvicorn bind is loopback; Compose overrides the container bind for port forwarding. |
| [compose.yaml](../../compose.yaml) | API published at host `127.0.0.1:8000` by default; existing runtime restrictions retained. PostgreSQL 17/pgvector 0.8.7 image pinned by digest, internal-only database network, no database host port, readiness check and persistent `postgres_data` volume. A separately credentialed one-shot migration runs before API/tests. Optional test service runs inside the database network. This is not a complete execution sandbox. |
| [docker/postgres/001-init.sh](../../docker/postgres/001-init.sh) | First-run initialization enables vector and creates the restricted `sdlc_app` login; API receives no bootstrap-admin password. No application schema is created. |
| [tests/test_api.py](../../tests/test_api.py), [tests/test_policy.py](../../tests/test_policy.py) | API smoke checks and selected policy checks for reads, scope mismatch, A0 writes, approval matching/expiry, unavailable audit and production denial. |

The database foundation retains read-only [connectivity integration tests](../../tests/test_database_integration.py). New [workflow integration tests](../../tests/test_workflow_integration.py) add synthetic state and approval fixtures, including fresh-process retrieval and internal resume checks. [app/migrate.py](../../app/migrate.py) owns additive checkpoint/registry schema setup; runtime credentials cannot perform DDL or issue approvals. There is no authenticated approval issuer, audit store, LLM provider integration, OpenHands runner, RAG or external service integration. Project/run IDs do not establish authenticated tenant isolation. See [workflow persistence](workflow-persistence.md) for lifecycle, identity, privileges and failure semantics.

## Future plans — not implemented

The [README roadmap](../../README.md) proposes authenticated APIs/project membership, authenticated approval issuance, append-only audit and enforcement on every future tool adapter; checkpoint recovery/retention/version migration; isolated OpenHands execution; project-scoped RAG; and staged read-only integrations followed by separately authorized narrow writes.

Authentication, trusted project membership, authenticated approval issuance, durable audit, robust recovery/retention and future integrations require separate tasks and security review. Task 003 adds checkpoints and internal interrupt/resume, without exposing unauthenticated resume or implementing RAG. Provider independence currently means shared coding-agent instructions; it does not imply a model-provider abstraction. See [security guardrails](security.md) before extending trust boundaries.
