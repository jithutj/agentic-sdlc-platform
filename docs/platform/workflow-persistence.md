# Persistent draft workflow

## Scope and lifecycle

Docker Compose runs the deterministic draft workflow with PostgreSQL checkpoints. The Python-only demo defaults to a request-local memory checkpointer for compatibility. Set `WORKFLOW_PERSISTENCE=postgres` with the documented `DB_*` settings to require persistence; configured PostgreSQL failures return a redacted 503, never a silent memory fallback.

1. `POST /draft` accepts the existing task fields. The server creates an immutable registry entry and a UUID4 `thread_id`.
2. The draft node produces `DRAFT ONLY: <objective>` and sets `awaiting_human_review`.
3. The review node calls LangGraph `interrupt()`. Synchronous checkpoint writes finish before the response. The pending review survives API process/container restarts.
4. A trusted in-process lookup can retrieve the stored state using the exact project, run and opaque thread ID. There is no HTTP lookup endpoint.
5. An internal resume validates an independently provisioned server-side approval, reserves it once, and calls `Command(resume=...)`. The review node re-enters, receives the validated approval ID and finishes with `human_reviewed`. It performs no external action.

The response preserves the original five fields and adds `thread_id`. In PostgreSQL mode, repeating a project/run returns HTTP 409 `{"status":"run_already_exists"}` regardless of objective. It never returns, overwrites or resumes an existing draft. Use a new run ID for a new draft. Memory previews are not durable and do not enforce duplicate-run detection.

A checkpoint is comparable to saving a NestJS job's execution state in PostgreSQL. An interrupt ends the current invocation after saving its place; it does not hold an HTTP request or PHP worker open. Resume is a new invocation, comparable to a later queue job loading saved progress. The interrupted node starts again, so code before `interrupt()` must remain free of side effects. See the [LangGraph interrupt lifecycle](https://docs.langchain.com/oss/python/langgraph/interrupts).

## Identity and access boundary

`workflow.runs` maps the unique `(project_id, run_id)` pair to a server-generated UUID4 `thread_id`, objective SHA-256 digest and graph version `draft-review-v1`. The mapping is persistent, not derived by concatenating caller strings. Runtime SQL privileges allow inserting/reading run records, but not changing or deleting identities. Future retries/lookups retain the recorded thread ID; caller-provided thread IDs are not accepted by `/draft`.

Every internal lookup/resume checks all three identifiers against the registry before loading a checkpoint. The loaded state's project, run, thread, graph version and objective digest must match that registry. Callers cannot select arbitrary checkpoint IDs or supply raw LangGraph config. Session advisory locks serialize operations per thread across processes; a unique project/run constraint prevents concurrent creates from overwriting each other.

These checks prevent identity confusion; they are **not authenticated tenant isolation**. Project IDs are caller labels, and a thread handle is not proof of human identity. The compatibility API has no authentication. RED-6 authenticates only a narrow intake service; neither listener exposes lookup, approval issuance or resume routes. In-process code and local database operators are trusted. Raw checkpoint access is not an authorization API. Real project membership, authenticated principals and scoped authorization must precede any external retrieval or resume surface.

## Migration and permissions

The existing first-run Postgres script still creates `vector` and `sdlc_app`. The new one-shot `migrate` service uses the separate local bootstrap-admin credential and runs `python -m app.migrate`. It creates the private `workflow` schema, calls the pinned PostgreSQL checkpointer's `setup()`, creates registry/approval tables and grants only required runtime access. The API never calls `setup()` and never receives the admin password.

| Runtime object | `sdlc_app` privileges |
| --- | --- |
| `runs`, `approval_uses`, `intake_events` | SELECT, INSERT |
| `approvals` | SELECT only |
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` | SELECT, INSERT, UPDATE |
| `checkpoint_migrations` | None |
| `workflow` schema | USAGE only, no CREATE |

Migration uses a session lock and autocommit because upstream setup includes concurrent index creation. Setup is additive and repeatable for the pinned versions. Existing Phase 1A volumes are retained; no database reset or new password is required. Partial failures stop startup and can be retried after diagnosing the error. The API depends on successful migration in Compose.

The migration account is the local bootstrap admin, not a production least-privilege migration role. API credentials still access checkpoints for all projects; database row-level tenant security is not implemented. Checkpoint deserialization uses an explicit empty custom-module allowlist and no pickle fallback. See the [checkpointer connection/setup requirements](https://pypi.org/project/langgraph-checkpoint-postgres/).

## Internal approval and resume contract

The trusted service in [workflow_store.py](../../app/workflow_store.py) provides:

```python
from app.workflow_store import open_workflows

with open_workflows() as workflows:
    state = workflows.read(project_id, run_id, thread_id)
    pending = workflows.pending_review(project_id, run_id, thread_id)
    # Resume only after an independent trusted issuer records a valid approval.
    state = workflows.resume(project_id, run_id, thread_id, approval_id)
```

No production approval issuer or operator approval CLI is provided. Integration tests insert synthetic approvals through a separately credentialed admin connection. A future independently authenticated local approval mechanism must review the actual draft and record an approval ID, immutable thread, exact pending checkpoint ID, state digest, verified approver ID and expiry. The runtime role cannot insert or edit these records. Caller approval flags and the existing demo `Approval` model are not used to authorize workflow resume.

Resume verifies the current real interrupt, exact identity, checkpoint, digest and expiry. An atomic insert into `approval_uses` reserves the approval before executing the graph. Replays and concurrent attempts are denied. If a process fails after reservation but before completion, that approval remains consumed; a trusted operator must inspect state and issue a fresh approval if still appropriate. This deliberately favors denial over accidental replay; it is not an exactly-once transaction across all checkpoint writes.

## Setup, proof and rollback

Follow the [README Docker setup](../../README.md). With the existing private `.env` configured:

```bash
docker compose config --quiet
docker compose up --build -d --wait
docker compose run --rm migrate
docker compose --profile test run --build --rm tests
```

The explicit second migration checks repeatability. `--rm` removes disposable command containers, not the database volume. Runtime and migrations use bounded connect/query/lock waits; these are not a whole-request deadline including DNS and multiple graph steps.

Unit tests run with `pytest -q`. PostgreSQL tests require `RUN_WORKFLOW_INTEGRATION=1`, `WORKFLOW_PERSISTENCE=postgres`, the runtime `DB_*` settings and `CHECKPOINT_TEST_ADMIN_PASSWORD` for synthetic approval fixtures. Compose supplies these only to its test service. Tests add synthetic runs/checkpoints/approvals and retain them; use an isolated test project/volume, never customer or production data. The original connectivity tests remain read-only.

Tests cover real interrupts, fresh-process retrieval, duplicate creates, project/run/thread isolation, stored-identity tampering, runtime permission denial, approval mismatch/expiry/replay, concurrent resume, and failure after reservation. HTTP tests verify absent approval/resume routes and ignored caller approval flags.

For container-restart proof, create a synthetic draft with a unique project/run and record its returned thread ID. Replace `PROJECT`, `RUN` and `THREAD` below with those values:

```bash
docker compose exec -T api python - PROJECT RUN THREAD <<'PY'
import json, sys
from app.workflow_store import open_workflows
with open_workflows() as workflows:
    print(json.dumps({"state": workflows.read(*sys.argv[1:]),
                      "pending": workflows.pending_review(*sys.argv[1:])}, sort_keys=True))
PY
docker compose up -d --force-recreate --no-deps api
```

Repeat the lookup after recreation and compare both state and pending checkpoint. No unauthenticated retrieval endpoint is added for this test.

Rollback means stopping the new API and running the previous Phase 1A application against the existing database, leaving the additive `workflow` schema and volume intact. The previous API does not read these checkpoints; persisted reviews remain unavailable until the compatible version returns. Do not drop schema, tables or volumes. Future dependency/graph/schema changes need a compatibility migration before existing threads can resume.

Known limits: no general user authentication, human approval issuer, SQL tenant security, durable platform audit service, retry/recovery UI or checkpoint retention policy. A failure after registry insertion may leave a reserved run with incomplete state; `/draft` returns 503 initially and 409 on later creates, rather than overwriting it. Trusted operators must diagnose such runs. There are no LLM calls, RAG or Codex execution. RED-6 adds only read-only Linear lookup and manually invoked Windmill intake.

## RED-6 durable intake

The additive migration creates `workflow.intake_events`. It records a unique `(project_id, issue_id)` event, first idempotency key, normalized task/configuration/server-plan digest, immutable run/thread binding and creation time. The runtime role can SELECT/INSERT but cannot UPDATE/DELETE this table. The original graph/version and approval tables are unchanged.

Intake serializes by project/issue before checking the registry. It atomically inserts the run and event records, then invokes the existing graph with synchronous checkpoint writes. The fixed objective includes the complete deterministic plan and QA text, so the review checkpoint/state digest covers that artifact. A repeat with the same task and trusted identity returns the saved run/thread and status even with a fresh transport key. Reusing a key or event with conflicting task/identity returns 409. The first transport key remains recorded; alternate retry keys are not separately logged. This is one manual planning event per pilot issue, not a general event-versioning system.

A successful retry requires fresh token authorization and a fresh validated read-only Linear lookup. It cannot recover data after authorization/configuration changes or an upstream outage by bypassing validation. Read/retry never calls `Command(resume=...)`. Existing `/draft` still rejects duplicate project/run pairs with 409 and never returns state on duplicate creation.

There is deliberately no claim of an atomic transaction spanning registry insertion and all LangGraph writes. A crash before a complete checkpoint can leave an immutable reserved event; the first request and later incomplete-state retries fail closed with a redacted 503. Operators must inspect such events; no automatic reset/replay/recovery tool is included. Completed interrupted runs survive normal container restarts and retry without state changes.

Run `python3 scripts/verify_red6.py` for repeatable Docker restart evidence. It uses a new project and synthetic secrets, real Windmill jobs and private HTTP, and **simulated Linear responses**. It records state and pending checkpoint, recreates DB/API/intake/Windmill containers with retained volumes, compares both snapshots, and runs another authenticated duplicate. It also runs all database and approval regressions. This proves the tested local interruption boundary, not arbitrary crash recovery or a live credentialed Linear integration.

Rollback keeps the additive table, Windmill database and all named volumes intact. Stop the new services and run the previous compatible API; existing `draft-review-v1` checkpoints remain compatible. The previous API ignores intake metadata. Do not drop roles/databases/schema or rotate credentials as an implicit rollback. See [deployment](../development/deployment.md) for privileged migration ownership and the separate Windmill database.
