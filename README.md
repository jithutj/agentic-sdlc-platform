# Agentic SDLC Platform — Local Starter v0.1

**Scope:** Demonstrates a minimal LangGraph draft-only workflow, FastAPI endpoint and deterministic policy decision function. **Not a working autonomous coding platform.** No OpenHands, RAG, database, durable checkpoints, authenticated approval service, external integrations or production-ready isolation are implemented.

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

Optional on Linux/WSL2: `docker compose up --build` (Docker Engine required). Docker Desktop networking and host-mode support vary; use Python venv first if needed.

## Security limitations

- API is unauthenticated and MUST stay on localhost. Never publish it or attach real tokens.
- `authorize()` is a testable policy function, **not** wired to external tools. A2 approval objects are caller-supplied; real approvals require independently authenticated human identity, immutable records and one-time consumption.
- No production or merge operations exist. No arbitrary shell execution, GitHub writes, Linear writes or model calls exist.
- Workflow state is in-memory and not restart-durable; this is a Phase 0 scaffold only.
- Docker Compose example uses Linux host networking for localhost binding and is not a full hardened sandbox.
- Pin dependencies and scan images before any real deployment.

## Next implementation gates

1. Add authenticated API, project registry, durable Postgres state, append-only audit and deny-by-default PEP wired to *every* tool adapter.
2. Implement server-issued, one-time human approval bound to exact resource and artifact digest.
3. Add LangGraph durable checkpoints, interrupt/resume and restart tests.
4. Add isolated OpenHands execution without host Docker socket, credentials or unrestricted network.
5. Add project-scoped LangChain RAG and SEC-01..SEC-12 tests.
6. Only then connect Linear/GitHub read-only; separately authorize narrow writes.

## Documentation

- [AGENTS.md](AGENTS.md): shared coding-agent instructions and selective context loading.
- [CLAUDE.md](CLAUDE.md): thin Claude Code adapter to the shared instructions.
- [Development workflow](docs/development/workflow.md): local development, validation and agent handoffs.
- [Platform architecture](docs/platform/architecture.md): confirmed implementation and clearly separated future plans.
- [Security guardrails](docs/platform/security.md): minimum development boundaries and current limitations.

This repository builds a reusable platform, not the Redeeming Light website. Project-specific documents stay outside default coding-agent context and are loaded only for relevant tasks. Previously named platform/security/project reference documents are not present here; their contents are not assumed by this documentation.
