# RED-5 pilot and RED-6 integration

This file is project-specific context. Load it only for this pilot; it is not default platform-agent context.

## Verified scope

Read-only connector inspection on 2026-11-23 confirmed:

| Binding | Value |
| --- | --- |
| Linear workspace | Redeeming Light, `03c2cfb9-397c-44ae-94c8-21c0d5600749` |
| Team | `RED`, `892527f6-5f90-4151-8f86-806023d2185e` |
| Pilot issue | [RED-5](https://linear.app/redeeming-light/issue/RED-5/build-astro-frontend-foundation-agent-delivered-qa-gated), `db242cb9-156b-4349-8dcc-3e889e110f8e` |
| Linear project assignment | Unassigned (`projectId: null`); configure explicit `none`, never a wildcard |
| Platform project | `redeeming-light` |
| Repository | `jithutj/redeeminglight` |
| Integration issue | [RED-6](https://linear.app/redeeming-light/issue/RED-6/build-windmill-langgraph-sdlc-platform-pilot-a1-scaffold) |

The connected read-only lookup is configuration evidence, not proof that Docker has accessed Linear with a runtime key. Reverify these bindings before using a live development credential. QMO/Quick Menu Order and all other projects/repositories/issues are denied. Repository authorization is a fixed platform allowlist, not inferred from issue prose. If the issue later joins a Linear project, review and update the exact configured UUID; the existing `none` binding must reject it.

RED-5 requests an Astro frontend foundation. This integration only produces a deterministic local planning draft and QA plan. It does not edit that repository or complete RED-5. RED-6 consolidates the candidate connector into the existing platform and preserves durable LangGraph review; it does not authorize publication or live Codex execution.

## Manual live development run

1. Start the normal stack using [deployment](../../development/deployment.md), without the simulation overlay. Replace Windmill bootstrap credentials and create a restricted local workspace/folder for the reviewed connector.
2. Configure a narrowly scoped read-only development Linear credential. Do not use a production key or a key belonging to QMO. The code sends only a fixed GraphQL query; credential-level read restrictions must also be configured by the operator. Store the API's credential in private `.env` as `LINEAR_READ_API_KEY`.
3. Set the API's `PILOT_LINEAR_WORKSPACE_ID`, `PILOT_LINEAR_TEAM_ID`, `PILOT_LINEAR_ISSUE_UUID` to the verified values above and `PILOT_LINEAR_PROJECT_ID=none`. Set a distinct local `PILOT_INTAKE_TOKEN` of at least 32 characters. Recreate `intake` through `docker compose up -d --wait intake` after configuration changes.
4. In Windmill, create folder `platform`. Create secret variables `f/platform/pilot_token` matching the intake token and `f/platform/linear_read_key` holding a read-only development Linear key. Limit access to the trusted connector operator. Use plain variables `f/platform/workspace_id`, `f/platform/team_id`, `f/platform/issue_uuid`, `f/platform/linear_project_id` with the verified values. Never pass secrets as job arguments.
5. Import [red5_linear_dispatch.py](../../../windmill/red5_linear_dispatch.py) as a Python script. It declares the pinned `wmill==1.875.0` SDK dependency in its requirements header; preserve the resolved script lock. Its HTTP/validation logic otherwise uses the standard library. Its only argument is `issue_id`, default `RED-5`; the FastAPI URL and A1/draft contract are fixed. Do not add arbitrary URL or shell parameters.
6. Invoke it manually. It fetches identity-only Linear data, verifies all configured bindings, and calls `http://intake:8000/v1/intake`. FastAPI independently repeats the Linear lookup. Review the returned run/thread identifiers and `awaiting_human_review`; both execution/write flags must be false.
7. Repeat unchanged. Expect the same run/thread/status and unchanged pending checkpoint. A changed contract/configuration must conflict or fail scope checks. Do not reset the event to force another run; this pilot supports one planning event per issue.
8. Inspect private job diagnostics without exposing secrets. Confirm no issue/repository changes and record actual command/job evidence. Do not enable polling, public webhooks, approval/resume routes or autonomous coding.

The intake contract requires `project_id`, `issue_id`, `repository` and a bounded objective; `authorization` defaults to and permits only `A1`, and `operation` only `draft`. It rejects extra fields such as approval flags, capabilities, commands and thread IDs. The script sends a stable SHA-256 idempotency key. FastAPI persists the event independently of Windmill job identity; successful retries never invoke graph resume.

## Simulation and remaining gate

Run `python3 scripts/verify_red6.py` from repository root for a new isolated Docker project with synthetic secrets. It uses the real connector, Windmill worker, HTTP intake, PostgreSQL and LangGraph, while replacing only Linear responses in explicitly test-only code. This does not validate the live runtime credential, Linear API compatibility or production isolation.

See [validation evidence](../../development/red6-validation.md) for actual results. A live handoff requires the operator-managed read-only credential and normal-stack configuration. No live success or RED-5 completion is claimed by offline tests. Human approval issuance and isolated Codex execution remain unimplemented.

## Project source revisions needed later

The SOURCE package names `RL-CONTEXT-001 v2.0`, `AI-PLATFORM-CONTEXT-001 v1.0` and `AI-SEC-001 v1.0`. Their bodies were not available for verification; they are not evidence or permission. Their owners should reconcile the chosen Windmill/FastAPI/LangGraph/PostgreSQL/Codex split, local-only service-token pilot, exact project binding, independent approval gate, persistence and security limitations. Do not assume undocumented requirements or revise those sources without authorization.

The read RED-6 issue still describes separate ZIP artifacts and historic mocked results. A future authorized revision should link the consolidated repository, decision record and new evidence, preserving historical claims as history. RED-5 should continue to distinguish planning from delivered/QA-approved code. No remote issue or project document was changed in this task.
