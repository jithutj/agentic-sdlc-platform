# RED-5 pilot and RED-6 integration

This file is project-specific context. Load it only for this pilot; it is not default platform-agent context.

## Verified scope

Read-only connector inspection on 2026-11-23 confirmed the Redeeming Light workspace, RED team and RED-5 UUID with an unassigned Linear project. The exact editable identity values and all six Windmill variable mappings now live in [the quickstart](../../quickstart.md), the single onboarding source.

Integration issue: [RED-6](https://linear.app/redeeming-light/issue/RED-6/build-windmill-langgraph-sdlc-platform-pilot-a1-scaffold). Platform project: `redeeming-light`. Repository allowlist: `jithutj/redeeminglight`.

The connected read-only lookup is configuration evidence, not proof that Docker has accessed Linear with a runtime key. Reverify these bindings before using a live development credential. QMO/Quick Menu Order and all other projects/repositories/issues are denied. Repository authorization is a fixed platform allowlist, not inferred from issue prose. If the issue later joins a Linear project, review and update the exact configured UUID; the existing `none` binding must reject it.

RED-5 requests an Astro frontend foundation. This integration only produces a deterministic local planning draft and QA plan. It does not edit that repository or complete RED-5. RED-6 consolidates the candidate connector into the existing platform and preserves durable LangGraph review; it does not authorize publication or live Codex execution.

## Manual live development run

Follow [the quickstart](../../quickstart.md) from initial Docker/WSL2 setup through the manual Windmill run. It replaces the former setup steps here and is authoritative for credentials, exact variable paths, script import, preflight and daily startup. This project record retains scope, history and remaining gates.

The intake contract requires `project_id`, `issue_id`, `repository` and a bounded objective; `authorization` defaults to and permits only `A1`, and `operation` only `draft`. It rejects extra fields such as approval flags, capabilities, commands and thread IDs. The script sends a stable SHA-256 idempotency key. FastAPI persists the event independently of Windmill job identity; successful retries never invoke graph resume.

## Simulation and remaining gate

Run `python3 scripts/verify_red6.py` from repository root for a new isolated Docker project with synthetic secrets. It uses the real connector, Windmill worker, HTTP intake, PostgreSQL and LangGraph, while replacing only Linear responses in explicitly test-only code. This does not validate the live runtime credential, Linear API compatibility or production isolation.

See [validation evidence](../../development/red6-validation.md) for actual results. A live handoff requires the operator-managed read-only credential and normal-stack configuration. No live success or RED-5 completion is claimed by offline tests. Human approval issuance and isolated Codex execution remain unimplemented.

## Project source revisions needed later

The SOURCE package names `RL-CONTEXT-001 v2.0`, `AI-PLATFORM-CONTEXT-001 v1.0` and `AI-SEC-001 v1.0`. Their bodies were not available for verification; they are not evidence or permission. Their owners should reconcile the chosen Windmill/FastAPI/LangGraph/PostgreSQL/Codex split, local-only service-token pilot, exact project binding, independent approval gate, persistence and security limitations. Do not assume undocumented requirements or revise those sources without authorization.

The read RED-6 issue still describes separate ZIP artifacts and historic mocked results. A future authorized revision should link the consolidated repository, decision record and new evidence, preserving historical claims as history. RED-5 should continue to distinguish planning from delivered/QA-approved code. No remote issue or project document was changed in this task.
