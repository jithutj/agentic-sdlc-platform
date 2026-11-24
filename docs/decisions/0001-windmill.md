# ADR 0001: Windmill Community for local execution and integrations

Status: selected for RED-6 local A0/A1 integration. Date: 2026-11-23.

## Context

The repository already owns a FastAPI control plane, PostgreSQL/pgvector, LangGraph checkpoints and a real human-review interrupt. RED-6 supplies a Python read-only connector candidate. The task selects Windmill Community and requires consolidation rather than a replacement application or a second agent-state store.

## Decision

Use Windmill Community for manual triggers, reviewed connector/job execution and operational diagnostics. Keep authentication, project authorization and durable intake deduplication in FastAPI; keep agent lifecycle/checkpoints and validated internal resume in LangGraph. Share the existing PostgreSQL cluster through a separate Windmill database/login. Codex CLI is the selected future runner, with execution disabled until isolation and security tests exist.

Windmill's documented [server/worker/PostgreSQL architecture](https://www.windmill.dev/docs/advanced/self_host) fits this split. The [upstream Compose configuration](https://github.com/windmill-labs/windmill/blob/v1.875.0/docker-compose.yml) supplies the server/worker modes. This repository deliberately omits optional enterprise/editor/proxy services and privileged worker settings. It reuses the candidate's Python connector shape and adds stricter verified identity and persistence boundaries.

## Alternatives

| Option | Assessment for this task |
| --- | --- |
| Windmill Community | Selected by the task; direct fit for the existing Python connector and distinct operational job versus agent checkpoint responsibilities. No commercial feature is required by this pilot. |
| Activepieces | A valid self-hosted automation alternative. Its [documented Compose setup](https://www.activepieces.com/docs/install/overview) includes PostgreSQL and Redis. Replacing the selected connector path would introduce additional migration/integration work without a demonstrated requirement in this pilot. Not imported. |
| n8n Community | A valid [self-hosted automation alternative](https://docs.n8n.io/hosting/). No existing n8n workflow is present to preserve; selecting it would require implementing a different handoff without improving a verified acceptance requirement. Not imported. |
| LangGraph alone | Retains agent orchestration but does not deliver the requested visual/manual operational execution layer. |

This is a scope/fit decision, not a performance, security or licensing superiority claim. No comparative benchmark or complete product evaluation was performed. Review product licenses and edition limits independently before broader distribution or production adoption.

## Consequences and superseded guidance

There is one platform codebase and one platform workflow-state authority. Windmill persists its own queue/job metadata, not a replacement LangGraph state. Two listeners run the same FastAPI application to protect localhost-only legacy routes from the worker network.

The initial worker is trusted operational infrastructure, not an isolated AI runner. Do not run arbitrary issue-derived code, attach production/model/GitHub credentials or mount a Docker socket. Real human approval remains independent; no Windmill button or model output authorizes a protected action.

This decision supersedes the SOURCE scaffold's separate application, in-memory idempotency, simplified terminal “Awaiting Approval” graph and advice to deploy an unrelated Windmill stack. It also supersedes repository roadmap references to OpenHands as the selected runner. Existing PostgreSQL checkpoints, graph version, review interrupt and one-use approval gate are preserved. Project-specific scope is documented only in the [pilot runbook](../projects/redeeming-light/pilot.md).

Local checks and simulations are listed in [validation evidence](../development/red6-validation.md). Production exposure, live credentialed integration, autonomous execution and external writes are separate gates.
