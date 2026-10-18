# ombuds — Build Task List

Extracted from the "🤖 AI Build" view of the AI Interview Notion database (snapshot — re-extract if the Notion board has moved on since this was pulled). Priority is tracked on the Notion board, not duplicated here; checkboxes below just track done vs. not.

## Week 1 — Raw API Fundamentals + Engineering Foundation

- [x] Design the folder structure to the project
- [x] Implement EU261 rules engine (`verticals/airline/rules.py`) + unit tests — [summary](task_summaries.md#implement-eu261-rules-engine-verticalsairlinerulespy--unit-tests)
- [x] Call OpenAI & Anthropic APIs directly, compare outputs — [summary](task_summaries.md#call-openai--anthropic-apis-directly-compare-outputs)
- [x] Stub `approval_gate` as deny-all before any state-changing tool is registered — [summary](task_summaries.md#stub-approval_gate-as-deny-all-before-any-state-changing-tool-is-registered)
- [x] Define tool schemas (`check_eligibility`, `log_claim`) + parse tool-use loop — [summary](task_summaries.md#define-tool-schemas-check_eligibility-log_claim--parse-tool-use-loop)
- [x] Build FastAPI `/triage` endpoint (raw SDK, no framework) — [summary](task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework)
- [x] Write unit tests for tool-calling parser + endpoint — [summary](task_summaries.md#write-unit-tests-for-tool-calling-parser--endpoint)
- [x] Implement streaming (SSE) + buffered JSON parsing — [summary](task_summaries.md#implement-streaming-sse--buffered-json-parsing)
- [x] Add structured output validation with Pydantic + retry/repair — [summary](task_summaries.md#add-structured-output-validation-with-pydantic--retryrepair)
- [x] Add retries/backoff, timeouts, fallback model, idempotency — [summary](task_summaries.md#add-retriesbackoff-timeouts-fallback-model-idempotency)

## Week 2 — Agentic Loop + MCP

- [x] Rebuild tool-calling loop in LangGraph — [summary](task_summaries.md#rebuild-tool-calling-loop-in-langgraph)
- [x] Stand up MCP server (`search_kb`, `check_eligibility`, `log_claim`, `issue_payment`) — [summary](task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment)
- [x] Connect LangGraph agent to tools over MCP — [summary](task_summaries.md#connect-langgraph-agent-to-tools-over-mcp)
- [x] Add short-term + long-term memory to agent state — [summary](task_summaries.md#add-short-term--long-term-memory-to-agent-state)
- [x] Add escalation/retry loop on low confidence — [summary](task_summaries.md#add-escalationretry-loop-on-low-confidence)
- [x] Replace deny-all stub with human-approval gate before state-changing tool calls — `log_claim`/`issue_payment` must be idempotent on `claim_id` (a retried or re-sent approval can't double-log/double-pay); see W1 review finding F-04 — [summary](task_summaries.md#replace-deny-all-stub-with-human-approval-gate-before-state-changing-tool-calls)

## Week 3 — RAG, Data Layer, Docker, Guardrails

- [x] Set up Postgres (relational) + pgvector/Chroma (embeddings) — [summary](task_summaries.md#set-up-postgres-relational--pgvectorchroma-embeddings)
- [x] Build RAG pipeline — chunk → embed → store → retrieve → cite — [summary](task_summaries.md#build-rag-pipeline--chunk--embed--store--retrieve--cite)
- [x] Build small eval set (20–30 Q/A pairs), measure retrieval quality — [summary](task_summaries.md#build-small-eval-set-2030-qa-pairs-measure-retrieval-quality)
- [x] Write Docker Compose for full stack, verify `docker compose up` — [summary](task_summaries.md#write-docker-compose-for-full-stack-verify-docker-compose-up)
- [x] Add PII filtering on inputs/outputs — [summary](task_summaries.md#add-pii-filtering-on-inputsoutputs)
- [x] Add prompt-injection test cases — [summary](task_summaries.md#add-prompt-injection-test-cases)
- [x] Write integration test for `/triage` end-to-end — [summary](task_summaries.md#write-integration-test-for-triage-end-to-end)

## Pre-W4 refactor (W3 review) — [plan](w3_review_pre_w4_plan.md)

- [x] P-1 — Composition-root wiring: approval store, pool and registry injected, `_GATE` removed — [summary](task_summaries.md#pre-w4-refactor-w3-review)
- [x] P-2 — Executors, durable `claims`, `payments` migration, ADR-0009 addendum — [summary](task_summaries.md#pre-w4-refactor-w3-review)
- [x] P-3 — Shared triage-run preamble, consistent escalation `answer` — [summary](task_summaries.md#pre-w4-refactor-w3-review)
- [x] P-4 — Docs reconciliation (AGENTS.md, README, tasks, summaries) — [summary](task_summaries.md#pre-w4-refactor-w3-review)

## Week 4 — Observability, Governance, Polish

- [ ] Add OpenTelemetry tracing (span per LLM/tool call)
- [x] Write one OPA/Rego policy (block auto-payout above €X) — [ADR-0015](../decisions/0015-opa-sidecar-over-embedded-evaluation.md), [summary](task_summaries.md#write-one-oparego-policy-block-auto-payout-above-x)
- [x] Build audit trail — log every tool call + decision — [ADR-0016](../decisions/0016-append-only-postgres-audit-log-at-the-governance-seams.md), [summary](task_summaries.md#build-audit-trail--log-every-tool-call--decision)
- [x] Write architecture diagram + README (problem, design, trade-offs) — [summary](task_summaries.md#write-architecture-diagram--readme-problem-design-trade-offs)

---

Tool names follow ADR-0004 (EU261 tool set, not generic helpdesk tools). Last synced with Notion 2026-09-24.

Per-task recaps (goal, files touched, libraries used) live in [`task_summaries.md`](task_summaries.md) — each item with a summary link above points to its entry. Library/framework glossary lives separately in [`glossary.md`](glossary.md).
