# RED-6 validation and documentation change summary

Date: 2026-11-23. Task branch: `feature/red-6-windmill-integration`, created directly from `main` at `c679d1d`. Unmerged `feature/004-llm-gateway` was left untouched. Implementation and validation were local; subsequent user authorization permits committing and pushing this task branch. No PR, remote issue update or production deployment was performed.

## Integration disposition

The authoritative BASE is this repository. SOURCE is the read-only candidate at `/home/jithutj/www/personal/RED-6-pilot-v2`. No third platform was created and SOURCE was not modified. All 19 SOURCE files matched the original candidate ZIP in a byte comparison.

| Component | Disposition |
| --- | --- |
| Existing FastAPI application, `/draft`, database/vector probe | Preserved. Added one restricted listener of the same app for Windmill; localhost compatibility remains unchanged. |
| PostgreSQL volume, runtime role and additive migration | Preserved. Added immutable intake metadata and a separate Windmill database/login on the same cluster. |
| Existing `draft-review-v1` LangGraph, checkpoint serializer, run binding, interrupt and internal approval/resume gate | Preserved without replacing the graph or exposing approvals. |
| SOURCE read-only Linear and manual handoff approach | Adapted into a self-contained script with exact workspace/team/issue/project verification, fixed private URL, secrets outside job arguments and independent FastAPI revalidation. |
| SOURCE second FastAPI application and process-memory idempotency | Rejected. The existing application and durable PostgreSQL registry own intake/state. |
| SOURCE simplified graph and terminal “Awaiting Approval” string | Rejected. A real persisted LangGraph interrupt remains the review boundary. Fixed planning/QA output is deterministic, not executed coding work. |
| SOURCE independent Compose/application/dependency setup | Rejected. The original Dockerfile, Compose services, volume and migration remain the foundation. |
| Codex, GitHub writes, Linear mutations, uncontrolled polling, RAG | Not imported or enabled. Codex CLI is a future isolated execution gate. |

## Executed checks

| Check | Actual result and evidence scope |
| --- | --- |
| Host `pytest -q` through `/tmp/red6-venv/bin/pytest -q` | **74 passed, 23 skipped** in 1.15 s. All skips require explicit database integration opt-in. Ran outside the restricted sandbox because sandboxed TestClient stalled before its first health response. |
| Initial normal Compose startup | Executed `docker compose --env-file /tmp/red6-test.env -p agentic-red6-check up --build -d --wait`; verified DB/API/intake/server/worker healthy after correcting the health URL and API publishing network. Windmill reported `database_healthy: true`, `workers_alive: 1`. |
| Docker PostgreSQL/regression suite | Initial run: **96 passed** in 3.79 s. Final acceptance run: **97 passed** in 3.86 s in the isolated acceptance stack, including both directions of database-access denial and a positive Windmill-role connection/privilege check. No database tests skipped in those runs. |
| Repeated additive migrations | Executed both `windmill-init` and `migrate` against retained test state; both completed successfully. No volume reset. |
| Complete Docker acceptance harness | **Passed**, exit code 0. Real worker handoff and duplicate retry succeeded. Exact state/pending checkpoint remained equal after database/API/intake/Windmill recreation, and another worker job returned the same run/thread. Linear alone was simulated. |
| Resolved Compose security boundaries | Verified no intake/DB host ports, loopback-only published ports, internal control/database networks, disjoint legacy API/worker networks, no privileged service and no Docker socket mount. No secret values printed. |
| Python/shell syntax | `python3 -m compileall -q app windmill scripts tests` and `sh -n docker/postgres/001-init.sh docker/postgres/windmill-init.sh` passed. |
| Documentation links and diff whitespace | **92 local links checked, 0 missing**. `git diff --check` passed. |
| Real Linear identity configuration lookup | Connected read-only Redeeming Light workspace/RED-5 lookup confirmed identifiers and unassigned project. It did not provide a runtime key or prove the container adapter's live GraphQL request. |

The tested environment used Python 3.12, Docker Engine 29.6.2 and Compose v5.3.1. [compose.yaml](../../compose.yaml) pins PostgreSQL/pgvector and Windmill Community image digests; [Dockerfile](../../Dockerfile) pins the Python base digest. [requirements.lock](../../requirements.lock) constrains resolved runtime/test package versions. This is not a hermetic build, artifact-signature verification or vulnerability-scan report.

### Complete harness record

Command: `python3 scripts/verify_red6.py`. The harness provisions new synthetic secrets and an isolated project, runs all tests and real Windmill worker jobs, checks duplicate intake, recreates containers and compares pending checkpoint/state. Linear responses are substituted explicitly in test-only code. Final result: **passed**, exit code 0, project `red6-verify-cc6e792db0`.

```json
{
  "result": "passed",
  "linear": "simulated",
  "windmill_worker": "real",
  "database": "real",
  "restart_checkpoint_equal": true,
  "retry_run_equal": true,
  "run_id": "938c2c8d-b864-4e6a-aee4-2ed5092044a4",
  "thread_id": "8c1e2a6b-9462-471a-9609-c4e5d42b9fd3",
  "suite": "97 passed in 3.86s"
}
```

The harness removed its test containers/networks and retained all volumes plus its mode-0600 synthetic env file at `/tmp/red6-verify-cc6e792db0-if0hm374.env`. Existing repository `.env` and unrelated stacks were not modified. No production deployment or real runtime Linear success is claimed.

Initial harness attempts exposed an exhausted local Docker subnet pool and Windmill's default automatic username creation rejecting an explicit username in the synthetic workspace request. Only this task's own test containers/networks were removed to free subnets; volumes were retained. The harness now releases its own networks in `finally` and reads the generated workspace username. Real worker runs also exposed signature-default parsing and missing SDK dependency declaration; both were corrected in the connector. No unrelated stack was stopped or changed.

## Coverage and limitations

Unit tests cover fail-closed/missing/wrong authentication before parsing, strict schema and body bounds, project/repository/issue denial, A2/write/self-approval rejection, redacted failures, missing trusted configuration, wrong Linear organization/team/issue/project and fixed private dispatch. Existing policy/workflow tests remain intact.

Docker tests exercise real vector queries, restricted runtime roles, durable checkpoints, exact project/run/thread binding, concurrent approval consumption, checkpoint/digest/expiry mismatch, failure after approval reservation, durable duplicate/conflicting intake and concurrent requests. Both platform-to-Windmill and Windmill-to-platform database connections are denied. Synthetic fixture approvals are created only through the separately credentialed test administrator; there is still no authenticated human approval issuer.

Not verified: live runtime Linear credential/API handoff, a delivered RED-5 website, AI execution, production deployment/readiness, vulnerability scanning, authenticated human approval, signed public event origin, general user tenancy/RLS, adversarial worker isolation or arbitrary crash recovery. A crash after registry insertion but before a complete checkpoint still needs operator diagnosis and fails closed. One planning event per pilot issue is intentional. Outbound networking is not domain-restricted. The trusted Windmill worker is not an AI sandbox.

## Changed-file inventory

- Runtime: `app/main.py`, `app/intake.py`, `app/workflow_store.py`, `app/migrate.py`, `pyproject.toml`, `requirements.lock`.
- Local infrastructure: `compose.yaml`, `compose.integration.yaml`, `Dockerfile`, `.env.example`, `docker/postgres/windmill-init.sh`.
- Connector/verification: `windmill/__init__.py`, `windmill/red5_linear_dispatch.py`, `windmill/README.md`, `scripts/verify_red6.py`.
- Tests: `tests/intake_fixture.py`, `tests/test_intake.py`, `tests/test_intake_integration.py`, `tests/test_windmill_dispatch.py`.
- Documentation: all files listed in the table below, excluding the connector guide already listed above. Existing `CLAUDE.md` remains the unchanged thin shared-instruction adapter.

## Documentation consolidation

| File | Change |
| --- | --- |
| [README](../../README.md) | Selected architecture, local Compose startup, new credentials, private intake flow, test harness, evidence links and Codex roadmap. Preserved accurate database and compatibility instructions. |
| [AGENTS.md](../../AGENTS.md) | Provider-neutral ownership, persistence, locality, read-only scope, approval and disabled-runner boundaries. No project business context added. |
| [Architecture](../platform/architecture.md) | Implemented responsibility split, reused graph/state, separate operational queue, restricted listener and tested/simulated/planned distinctions. |
| [Security](../platform/security.md) | Service-token versus authorization/approval, exact trusted binding, separate DB credentials, trusted-worker limitations and test-overlay prohibition on real stacks. |
| [Workflow persistence](../platform/workflow-persistence.md) | Immutable intake metadata, atomic registry insertion, duplicate behavior, exact restart proof, failure boundary and additive rollback. |
| [Development workflow](workflow.md) | Main-based branch, constrained installs, full Docker test/verification commands and handoff evidence rules. |
| [Deployment](deployment.md) | Environment table, Docker networks/volumes/health dependencies, resources, WSL2, migration/rollback and troubleshooting. |
| [ADR 0001](../decisions/0001-windmill.md) | Why Windmill was selected over Activepieces/n8n; tradeoffs and explicitly superseded SOURCE/OpenHands guidance. |
| [Pilot runbook](../projects/redeeming-light/pilot.md) and [connector guide](../../windmill/README.md) | RED-5/RED-6 scope, verified configuration, manual secret setup, live/simulated gate and source revision needs. |

Project source documents needing future authorized revision: `RL-CONTEXT-001 v2.0`, `AI-PLATFORM-CONTEXT-001 v1.0`, `AI-SEC-001 v1.0` (bodies unavailable), and RED-6's historic ZIP/scaffold status. Reconcile selected architecture, persistence, approval/worker boundaries and actual evidence without inventing unavailable source contents. RED-5 must continue to distinguish planning from delivered/QA-approved implementation. No remote documents were modified.

## Reproduce

Normal local stack, after updating private `.env` from [configuration guidance](deployment.md):

```bash
docker compose config --quiet
docker compose up --build -d --wait
docker compose --profile test run --build --rm tests
```

Isolated simulated-Linear acceptance:

```bash
python3 scripts/verify_red6.py
```

Live read-only development handoff requires the operator's scoped Linear credential and [pilot configuration](../projects/redeeming-light/pilot.md). Do not paste credentials into chat or source. Local simulation success alone does not close that gate.
