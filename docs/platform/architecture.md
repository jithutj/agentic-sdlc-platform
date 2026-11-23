# Platform architecture

## Confirmed implementation

The selected architecture is Windmill Community + FastAPI + LangGraph OSS + PostgreSQL/pgvector, with future isolated Codex CLI execution. The implementation remains a local A0/A1 demonstration, not an autonomous coding platform.

| Source | Confirmed behavior |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | Python >=3.11; FastAPI, Uvicorn, Pydantic, Psycopg 3, pinned LangGraph 1.2.22 and PostgreSQL checkpointer 3.2.1; pytest and httpx for development. Resolved Python runtime/test versions are constrained by [requirements.lock](../../requirements.lock). |
| [app/main.py](../../app/main.py), [app/database.py](../../app/database.py) | Unauthenticated `GET /health` reports local-demo mode and external writes disabled. `POST /draft` validates a task and invokes the graph synchronously. `GET /db-health` uses a read-only connectivity/vector probe. Workflow connections permit writes and bound statement/lock waits. Responses redact database errors; Python has no startup database dependency. |
| [app/models.py](../../app/models.py) | Task carries nonempty project/run IDs and objective, plus a level defaulting to A0. Action and Approval are data models. The draft route does not use the task's level to authorize execution. |
| [app/workflow.py](../../app/workflow.py), [app/workflow_store.py](../../app/workflow_store.py) | `START → draft → review → END`; deterministic draft followed by a genuine `interrupt()`. Compose uses PostgreSQL checkpoints; Python-only previews use request-local memory. Immutable run registry binds project/run to a server-generated thread UUID, objective digest and graph version. Internal lookup/resume checks identity; resume validates and reserves a one-use approval bound to the pending checkpoint/state digest. No HTTP lookup/approval/resume routes exist. |
| [app/policy.py](../../app/policy.py) | Standalone `authorize()` checks project/run scope, an audit-availability flag and capability/level rules. Reads are allowed at all defined levels; local drafts at A1–A3; PR/issue writes at A2–A3 require matching, unexpired caller-supplied approval data. Other capabilities are denied. No external write adapter exists. RED-6 intake separately enforces its fixed A1 draft contract; this policy function is not complete end-to-end tool authorization. |
| [Dockerfile](../../Dockerfile) | Python 3.12 slim runtime and test stages, UID/GID 65532. Default Uvicorn bind is loopback; Compose overrides the container bind for port forwarding. |
| [compose.yaml](../../compose.yaml) | API published at host `127.0.0.1:8000` by default; existing runtime restrictions retained. PostgreSQL 17/pgvector 0.8.7 image pinned by digest, separate internal database networks, no database host port, readiness checks and persistent `postgres_data` volume containing separate platform/Windmill databases. A separately credentialed one-shot migration runs before API/tests. Optional test service runs inside the database network. Windmill Community server/worker use the upstream server/worker modes with pinned images. The worker reaches only the private intake listener; the localhost compatibility listener shares no worker network. This is not a complete execution sandbox. |
| [docker/postgres/001-init.sh](../../docker/postgres/001-init.sh) | First-run initialization enables vector and creates the restricted `sdlc_app` login; API receives no bootstrap-admin password. No application schema is created. |
| [tests/test_api.py](../../tests/test_api.py), [tests/test_policy.py](../../tests/test_policy.py) | API smoke checks and selected policy checks for reads, scope mismatch, A0 writes, approval matching/expiry, unavailable audit and production denial. |

The database foundation retains read-only [connectivity integration tests](../../tests/test_database_integration.py). New [workflow integration tests](../../tests/test_workflow_integration.py) add synthetic state and approval fixtures, including fresh-process retrieval and internal resume checks. [app/migrate.py](../../app/migrate.py) owns additive checkpoint/registry schema setup; runtime credentials cannot perform DDL or issue approvals. RED-6 adds [app/intake.py](../../app/intake.py), a durable `workflow.intake_events` registry, and a [manual Linear dispatch script](../../windmill/red5_linear_dispatch.py). There is no authenticated human approval issuer, platform audit service, model integration, Codex runner, RAG or GitHub adapter. Project/run IDs do not establish authenticated tenant isolation. See [workflow persistence](workflow-persistence.md) for lifecycle, identity, privileges and failure semantics.

## Future plans — not implemented

The [README roadmap](../../README.md) proposes authenticated APIs/project membership, authenticated approval issuance, append-only audit and enforcement on every future tool adapter; checkpoint recovery/retention/version migration; isolated Codex CLI execution; project-scoped RAG; and staged read-only integrations followed by separately authorized narrow writes.

Broader user authentication/project membership, authenticated approval issuance, durable audit, robust recovery/retention and future integrations require separate tasks and security review. The pilot token authorizes one service/project/issue binding; it does not establish authenticated human identity or approval. Task 003 adds checkpoints and internal interrupt/resume, without exposing unauthenticated resume or implementing RAG. Provider independence currently means shared coding-agent instructions; it does not imply a model-provider abstraction. See [security guardrails](security.md) before extending trust boundaries.

## RED-6 responsibility split

| Boundary | Owns | Does not grant |
| --- | --- | --- |
| Windmill Community | Manual trigger, read-only Linear lookup, trusted connector execution, queue and operational job diagnostics | Human approval, agent execution authority, platform checkpoint ownership |
| FastAPI | Service authentication, bounded strict task validation, configured project/repository/issue authorization, independent Linear identity lookup, durable event deduplication | User-selected A2/A3, approval issuance, GitHub/Linear writes |
| LangGraph OSS | Existing `draft-review-v1` deterministic draft, real review interrupt, checkpoint lifecycle and internal validated resume | Tool authority or approval based on model output |
| PostgreSQL/pgvector | Platform run registry/checkpoints/approval reservations; separate Windmill database for jobs and secrets | Cross-database application access; pgvector does not imply RAG |
| Future Codex CLI runner | Planned isolated execution after independent review and security tests | No implementation or enabled execution path exists |

The same FastAPI application/image serves the loopback compatibility service and the restricted private intake service. They are not separate platform implementations. `/draft` preserves its old behavior; the private listener allows only `/v1/intake`, `/health` and `/db-health`.

For a manual run, Windmill validates the configured Linear organization, team ID/key, issue UUID/identifier and project assignment. FastAPI repeats that lookup using its own read-only configuration and credential. Issue descriptions, titles and attachments are not fetched or executed. The platform project/repository allowlist is server-owned. The complete fixed plan and QA text enter the existing graph as its saved draft objective; caller objective text is only schema-validated and hashed for conflict detection.

The platform event registry, not Windmill job IDs, owns agent run identity. A successful duplicate returns the same run/thread and saved status, including across API/DB/Windmill recreation. No automatic resume occurs. Windmill retains operational queue/job state separately; that is not a competing agent checkpoint store.

## Implementation and evidence status

- Implemented: existing persistence/interrupt/resume gate, restricted intake, read-only adapter, private Compose services and additive migration.
- Deterministic/simulated: planning output is a fixed draft, not AI work. Docker acceptance replaces Linear transport only in an explicit test overlay.
- Tested: see the exact commands and results in [validation evidence](../development/red6-validation.md); unit transport mocks are not live integration proof.
- Planned: live credentialed Linear acceptance, signed event origins, general tenancy, independent approval issuer, isolated Codex runner, scoped RAG, GitHub integration and all external writes.

Earlier OpenHands runner guidance and instructions to deploy Windmill as an unrelated stack are superseded by this architecture and the [decision record](../decisions/0001-windmill.md). Task 004's unmerged mock analyst branch is not part of this branch, which starts at `main` commit `c679d1d`.
