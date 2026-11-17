# Platform architecture

## Confirmed implementation

This repository is a local demonstration, not an autonomous coding platform.

| Source | Confirmed behavior |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | Python >=3.11; FastAPI, Uvicorn, Pydantic and LangGraph; pytest and httpx for development. Dependencies use version ranges. |
| [app/main.py](../../app/main.py) | Unauthenticated `GET /health` reports local-demo mode and external writes disabled. `POST /draft` validates a task and invokes the compiled graph synchronously. |
| [app/models.py](../../app/models.py) | Task carries nonempty project/run IDs and objective, plus a level defaulting to A0. Action and Approval are data models. The draft route does not use the task's level to authorize execution. |
| [app/workflow.py](../../app/workflow.py) | `START → draft → END`; the node prefixes the objective with `DRAFT ONLY:` and returns `awaiting_human_review`. State has project/run IDs, objective, draft and status. No model calls, tools, checkpointer or persistence are configured. The status is a returned string, not an approval interrupt. |
| [app/policy.py](../../app/policy.py) | Standalone `authorize()` checks project/run scope, an audit-availability flag and capability/level rules. Reads are allowed at all defined levels; local drafts at A1–A3; PR/issue writes at A2–A3 require matching, unexpired caller-supplied approval data. Other capabilities are denied. No API route or external tool adapter invokes it. |
| [Dockerfile](../../Dockerfile) | Python 3.12 slim image, UID/GID 65532, Uvicorn bound to `127.0.0.1:8000`. |
| [compose.yaml](../../compose.yaml) | One API service; host networking, read-only root filesystem, dropped capabilities, no-new-privileges, and PID/memory/CPU limits. This is not a complete execution sandbox. |
| [tests/test_api.py](../../tests/test_api.py), [tests/test_policy.py](../../tests/test_policy.py) | API smoke checks and selected policy checks for reads, scope mismatch, A0 writes, approval matching/expiry, unavailable audit and production denial. |

There is no database, authenticated approval service, audit store, LLM provider integration, OpenHands runner, RAG or external service integration. Project/run IDs are input fields and policy comparison values; they do not establish tenant isolation. Policy capability names do not imply implemented GitHub or issue-tracker access.

## Future plans — not implemented

The [README roadmap](../../README.md) proposes authenticated APIs, a project registry, durable Postgres state, append-only audit and enforcement on every tool adapter; server-issued one-time human approvals bound to exact resources and artifact digests; durable LangGraph checkpoints and interrupt/resume; isolated OpenHands execution; project-scoped RAG; and staged read-only integrations followed by separately authorized narrow writes.

These require separate tasks, designs and security review. This documentation bootstrap implements none of them. Provider independence currently means shared coding-agent instructions; it does not imply an implemented model-provider abstraction. See [security guardrails](security.md) before extending trust boundaries.
