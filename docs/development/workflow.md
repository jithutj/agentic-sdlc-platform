# Development workflow

## Working with coding agents

[AGENTS.md](../../AGENTS.md) is the shared instruction source. Codex uses it as the repository entry point; Claude Code reaches it through [CLAUDE.md](../../CLAUDE.md). For other agents, explicitly configure or supply `AGENTS.md` as the entry point; do not assume automatic discovery. Keep adapters thin and avoid copying the shared rules into provider files.

1. State the objective, allowed changes, acceptance checks and prohibited actions. Separate platform work from a particular project's requirements.
2. Inspect the relevant source, Docker configuration and tests. Load [architecture](../platform/architecture.md) or [security](../platform/security.md) only when relevant; do not load every document by default.
3. Make the smallest change that satisfies the task and preserves working behavior. Keep plans clearly separate from implemented functionality.
4. Validate the affected behavior. For documentation-only work, check local links and compare claims against source; do not change application code to match documentation.
5. Review the changed files for scope and secrets. Report the result, checks and remaining limitations. End the chat response with actionable commands and remaining manual UI steps, not only links to documentation. Commit or write to external services only when explicitly authorized.

For handoffs between Codex, Claude Code or another agent, provide the objective, changed files, checks already run and unresolved decisions. Reference shared instructions instead of duplicating them; do not include credentials or unrelated project context.

## Local development

Requires Python 3.11 or later. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -c requirements.lock -e '.[dev]'
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For Docker onboarding and daily startup, follow [the quickstart](../quickstart.md). Compose publishes the API only on host loopback and keeps PostgreSQL on a private internal network. The API container uses Python 3.12. Do not broaden the host bind address to make the demo accessible remotely.

The tests cover API health/draft responses, selected policy allow/deny cases and database-probe behavior. Opt-in integration tests validate PostgreSQL/pgvector, durable workflow interrupts, internal resume and runtime-role restrictions. Workflow tests retain additive synthetic records; use an isolated local test database. See [workflow persistence](../platform/workflow-persistence.md) for setup, authorization limits and restart proof. These checks do not establish production security or authenticated approval issuance.

## RED-6 validation and handoff

Create feature branches from `main`; keep unrelated unmerged branches separate. RED-6 begins at `c679d1d` and does not import Task 004. Preserve the existing checkpoints, review interrupt and approval tests when changing intake.

Use `pytest -q` for unit/regression checks. Run `docker compose --profile test run --build --rm tests` after normal Compose startup for all PostgreSQL checks. These tests add synthetic records and use admin credentials only for approval fixtures. New integration tests require the Windmill database initializer as well as platform migration, including cross-database CONNECT denial tests.

Run `python3 scripts/verify_red6.py` for the complete isolated Docker proof: generated synthetic secrets, real Windmill worker jobs, mocked Linear responses, authenticated private handoff, duplicate/conflict tests and checkpoint comparison across container recreation. It retains volumes and removes test containers/networks. Never reuse the simulation overlay on a normal stack. Report each test's actual result and clearly label the simulated dependency. Use [the quickstart](../quickstart.md) for onboarding and [deployment](deployment.md) for advanced configuration; use [validation evidence](red6-validation.md) for recorded results and limitations.

Python/pytest dependency versions are constrained in `requirements.lock`; Docker runtime image digests are pinned. When updating versions, regenerate constraints in an isolated environment, inspect the diff, run the full suite and repeat Docker acceptance. The lock is a version constraint set, not a package hash/signature verification system. Preserve graph-version compatibility and retained volumes.

## Project context

Redeeming Light is a separate project context, not this platform's implementation target. The RED-5 pilot runbook is present under `docs/projects/redeeming-light/`. Other project documents belong under `docs/projects/<project>/`, outside default agent context. Load only task-relevant documents on explicit need. This bootstrap introduces no RAG, embeddings or document ingestion.
