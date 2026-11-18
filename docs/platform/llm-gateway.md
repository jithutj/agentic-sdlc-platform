# LLM gateway and Requirements Analyst

## Implemented scope

Task 004 adds a provider-neutral structured-generation boundary, one deterministic mock adapter, and a Requirements Analyst. It makes no real LLM API calls and accepts no provider credentials. The mock uses a fixed template plus the objective's first 300 normalized characters; it does not understand domain rules or discover requirements. Its output is an untrusted draft, never authorization to act.

[llm.py](../../app/llm.py) defines Pydantic request/response contracts and the async `LLMClient` protocol. The request contains role/content messages, a JSON response schema, output-byte allowance and timeout; the response contains text and a completion/truncation indicator. The gateway enforces limits and validates response JSON against the agent's Pydantic model. It retries only explicit transient failures and timeouts. Malformed, truncated or oversized output is rejected without retry.

A Python `Protocol` is similar to a PHP interface or NestJS injection contract: the agent depends on methods, not a vendor SDK. An adapter can satisfy it without inheriting a particular base class. Future LiteLLM, Claude, OpenAI or local-model adapters must translate the same contracts, normalize failures, support cancellation and enforce transport/output limits. None is installed, registered or called here. Unknown provider selections fail closed.

The [Requirements](../../app/requirements.py) model requires summary, scope, out-of-scope, user stories (role/goal/benefit), acceptance criteria, assumptions and open questions. It rejects unknown fields, incorrect types, empty text/lists, NUL/invalid Unicode and excessive field/list sizes before PostgreSQL storage. Pydantic validation resembles NestJS DTO validation or validating a PHP service's return data before accepting it. See the [Pydantic model documentation](https://docs.pydantic.dev/latest/concepts/models/).

## API and execution

The existing `/health`, `/db-health` and `/draft` behavior is retained. `POST /analysis` is a separate entry point on the same localhost-only API:

```bash
curl -s http://127.0.0.1:8000/analysis \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"local-demo","run_id":"analysis-001","objective":"Describe a local issue tracker"}'
```

Use the configured `API_PORT` if different. The analysis DTO defaults to requested demo level A1 and checks the existing `draft:local` policy; A0 is denied. This policy check is not authenticated project membership. Callers cannot supply provider, limits, approval flags or thread IDs. Analysis IDs are limited to 128 characters; objective to 4,000 nonblank UTF-8 characters; the HTTP body is capped at 32 KiB, including chunked bodies. Validation failures do not echo submitted input.

The service assigns a UUID thread and records graph version `requirements-review-v1`. The graph runs `START`, `analyst`, then either the shared `review` node or `END` on failure. Success returns the structured `requirements`, `llm_usage`, a draft label and `awaiting_human_review`. The real interrupt includes the requirements marked `untrusted`. It is not an approval or an automated execution plan.

PostgreSQL mode checkpoints state through the existing saver. Internal lookups and resumes select the graph by the immutable registry version; old `draft-review-v1` threads retain their graph. Project/run uniqueness spans both entry points: reuse returns 409 without returning or overwriting existing state. There are no HTTP lookup, approval or resume endpoints. Internal resume retains exact project/run/thread checks and one-use server-side checkpoint/digest approval checks. Resuming a completed analyst at review does not call the provider again.

Failures persist as `analysis_failed` with a safe error code, no requirements and no review interrupt. API statuses are 413 for oversized HTTP bodies, 422 for invalid/over-limit input, 403 for policy denial, 409 for duplicate runs, 429 for budget rejection, 504 for provider/execution timeout, 502 for invalid output/provider failure/retry exhaustion, and 503 for configuration/database failures. Failed runs remain reserved; no public retry/reset API exists.

## Configuration and budget

Only server environment settings apply. Compose forwards these from private `.env`; `.env.example` contains safe defaults, not credentials:

| Setting | Default | Allowed range |
| --- | --- | --- |
| `LLM_PROVIDER` | `mock` | Only `mock` |
| `LLM_MAX_INPUT_CHARS` | 4000 | 1–4000 objective characters |
| `LLM_MAX_OUTPUT_BYTES` | 12000 | 1–16384 UTF-8 bytes |
| `LLM_MAX_ATTEMPTS` | 2 | 1–3 total attempts, including initial call |
| `LLM_TIMEOUT_SECONDS` | 1 | 0.01–10 per provider attempt |
| `LLM_RUN_TIMEOUT_SECONDS` | 3 | 0.01–30 for the gateway loop |
| `LLM_RUN_BUDGET_UNITS` | 60000 | 0–1000000 reserved byte-based units |

Budget units are **not tokens, currency or a real-provider spending guarantee**. Before every attempt, reserve the UTF-8 byte count of serialized messages/schema plus the entire output allowance. Failed attempts retain the full reservation; there are no refunds based on provider-reported usage. If the next reservation would exceed the run budget or attempt count, no provider call starts. A zero budget disables generation.

`workflow.llm_attempts` is an append-only ledger keyed by server thread and attempt number. The separately credentialed migration creates it; runtime receives SELECT/INSERT only. Reservations commit before attempts under the existing per-thread lock. Reconnection or a crash cannot reset consumed allowance. Limits are captured in the initial checkpoint; changing environment settings affects new runs. A crash before a node result may consume allowance without producing requirements; a future trusted recovery path must respect remaining reservations.

Gateway timeouts use cancellable async calls via [asyncio timeout handling](https://docs.python.org/3.12/library/asyncio-task.html#timeouts). They govern provider attempts and the gateway loop, not the entire HTTP upload, database connection, checkpoint lifecycle or OS scheduling. Database statements/locks keep their own bounds. The mock never blocks on network I/O. Non-cooperative or CPU-bound adapters are unsupported; future real adapters need transport deadlines, cancellation proof and response limits before buffering. No background retry worker or global concurrency/rate limit is implemented.

## Setup, tests and limits

Follow [README setup](../../README.md), preserve existing database passwords/volumes, then run:

```bash
docker compose config --quiet
docker compose up --build -d --wait
pytest -q
docker compose --profile test run --build --rm tests
```

Compose uses PostgreSQL and runs the additive migration first. The standalone Python demo still uses request-local memory previews unless `WORKFLOW_PERSISTENCE=postgres` and `DB_*` are explicitly configured. Python does not load `.env` automatically. Memory previews do not provide durable budget accounting or cross-request uniqueness.

[Gateway tests](../../tests/test_llm.py) and [API tests](../../tests/test_analysis.py) cover deterministic offline output, schema rejection, timeout/cancellation, retries, size/budget limits, policy denial and error redaction. [Integration tests](../../tests/test_analysis_integration.py) use the existing `RUN_WORKFLOW_INTEGRATION=1` opt-in and separate test admin credential. They cover checkpoint reconstruction in a fresh process, project/run isolation, persistent reservations, failed-run denial and authorized internal resume without regeneration. Integration tests add synthetic records and retain them; use a separate local test project/volume. The [persistence restart procedure](workflow-persistence.md) also works for analysis threads.

The gateway does not log prompts, raw responses or raw provider/parser exceptions. Contract representations hide content; safe error codes enter checkpoints. However, workflow state deliberately stores objectives and generated requirements and returns them to the creating caller. Use synthetic data, never secrets or customer data. Do not enable SDK/tracing body capture. Authentication, tenant isolation, real provider adapters/pricing, durable audit, retention and independent approval issuance remain future work. No RAG, code execution, deployment or external integrations are added.
