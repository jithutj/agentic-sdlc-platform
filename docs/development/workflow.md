# Development workflow

## Working with coding agents

[AGENTS.md](../../AGENTS.md) is the shared instruction source. Codex uses it as the repository entry point; Claude Code reaches it through [CLAUDE.md](../../CLAUDE.md). For other agents, explicitly configure or supply `AGENTS.md` as the entry point; do not assume automatic discovery. Keep adapters thin and avoid copying the shared rules into provider files.

1. State the objective, allowed changes, acceptance checks and prohibited actions. Separate platform work from a particular project's requirements.
2. Inspect the relevant source, Docker configuration and tests. Load [architecture](../platform/architecture.md) or [security](../platform/security.md) only when relevant; do not load every document by default.
3. Make the smallest change that satisfies the task and preserves working behavior. Keep plans clearly separate from implemented functionality.
4. Validate the affected behavior. For documentation-only work, check local links and compare claims against source; do not change application code to match documentation.
5. Review the changed files for scope and secrets. Report the result, checks and remaining limitations. Commit or write to external services only when explicitly authorized.

For handoffs between Codex, Claude Code or another agent, provide the objective, changed files, checks already run and unresolved decisions. Reference shared instructions instead of duplicating them; do not include credentials or unrelated project context.

## Local development

Requires Python 3.11 or later. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Alternatively, follow the [README](../../README.md) to configure `.env` and run `docker compose up --build`. Compose publishes the API only on host loopback and keeps PostgreSQL on a private internal network. The API container uses Python 3.12. Do not broaden the host bind address to make the demo accessible remotely.

The tests cover API health/draft responses, selected policy allow/deny cases and database-probe behavior. Opt-in integration tests validate PostgreSQL/pgvector, durable workflow interrupts, internal resume and runtime-role restrictions. Workflow tests retain additive synthetic records; use an isolated local test database. See [workflow persistence](../platform/workflow-persistence.md) for setup, authorization limits and restart proof. These checks do not establish production security or authenticated approval issuance.

## Project context

Redeeming Light is a separate project context, not this platform's implementation target. No project documents are currently present. Future project documents belong under `docs/projects/<project>/`, outside default agent context. Load only task-relevant documents on explicit need. This bootstrap introduces no RAG, embeddings or document ingestion.
