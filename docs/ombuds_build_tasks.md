# ombuds — Build Task List

Extracted from the "🤖 AI Build" view of the AI Interview Notion database (snapshot — re-extract if the Notion board has moved on since this was pulled). Priority is tracked on the Notion board, not duplicated here; checkboxes below just track done vs. not.

## Week 1 — Raw API Fundamentals + Engineering Foundation

- [x] Design the folder structure to the project
- [x] Implement EU261 rules engine (`verticals/airline/rules.py`) + unit tests — [summary](ombuds_build_task_summaries.md#implement-eu261-rules-engine-verticalsairlinerulespy--unit-tests)
- [x] Call OpenAI & Anthropic APIs directly, compare outputs — [summary](ombuds_build_task_summaries.md#call-openai--anthropic-apis-directly-compare-outputs)
- [x] Stub `approval_gate` as deny-all before any state-changing tool is registered — [summary](ombuds_build_task_summaries.md#stub-approval_gate-as-deny-all-before-any-state-changing-tool-is-registered)
- [x] Define tool schemas (`check_eligibility`, `log_claim`) + parse tool-use loop — [summary](ombuds_build_task_summaries.md#define-tool-schemas-check_eligibility-log_claim--parse-tool-use-loop)
- [x] Build FastAPI `/triage` endpoint (raw SDK, no framework) — [summary](ombuds_build_task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework)
- [x] Write unit tests for tool-calling parser + endpoint — [summary](ombuds_build_task_summaries.md#write-unit-tests-for-tool-calling-parser--endpoint)
- [x] Implement streaming (SSE) + buffered JSON parsing — [summary](ombuds_build_task_summaries.md#implement-streaming-sse--buffered-json-parsing)
- [x] Add structured output validation with Pydantic + retry/repair — [summary](ombuds_build_task_summaries.md#add-structured-output-validation-with-pydantic--retryrepair)
- [x] Add retries/backoff, timeouts, fallback model, idempotency — [summary](ombuds_build_task_summaries.md#add-retriesbackoff-timeouts-fallback-model-idempotency)

## Week 2 — Agentic Loop + MCP

- [x] Rebuild tool-calling loop in LangGraph — [summary](ombuds_build_task_summaries.md#rebuild-tool-calling-loop-in-langgraph)
- [x] Stand up MCP server (`search_kb`, `check_eligibility`, `log_claim`, `issue_payment`) — [summary](ombuds_build_task_summaries.md#stand-up-mcp-server-search_kb-check_eligibility-log_claim-issue_payment)
- [x] Connect LangGraph agent to tools over MCP — [summary](ombuds_build_task_summaries.md#connect-langgraph-agent-to-tools-over-mcp)
- [x] Add short-term + long-term memory to agent state — [summary](ombuds_build_task_summaries.md#add-short-term--long-term-memory-to-agent-state)
- [x] Add escalation/retry loop on low confidence — [summary](ombuds_build_task_summaries.md#add-escalationretry-loop-on-low-confidence)
- [ ] Replace deny-all stub with human-approval gate before state-changing tool calls — `log_claim`/`issue_payment` must be idempotent on `claim_id` (a retried or re-sent approval can't double-log/double-pay); see W1 review finding F-04

## Week 3 — RAG, Data Layer, Docker, Guardrails

- [ ] Set up Postgres (relational) + pgvector/Chroma (embeddings)
- [ ] Build RAG pipeline — chunk → embed → store → retrieve → cite
- [ ] Build small eval set (20–30 Q/A pairs), measure retrieval quality
- [ ] Write Docker Compose for full stack, verify `docker compose up`
- [ ] Add PII filtering on inputs/outputs
- [ ] Add prompt-injection test cases
- [ ] Write integration test for `/triage` end-to-end

## Week 4 — Observability, Governance, Polish

- [ ] Add OpenTelemetry tracing (span per LLM/tool call)
- [ ] Write one OPA/Rego policy (block auto-payout above €X)
- [ ] Build audit trail — log every tool call + decision
- [ ] Write architecture diagram + README (problem, design, trade-offs)

---

Tool names follow ADR-0004 (EU261 tool set, not generic helpdesk tools). Last synced with Notion 2026-09-24.

Per-task recaps (goal, files touched, libraries used) live in [`ombuds_build_task_summaries.md`](ombuds_build_task_summaries.md) — each item with a summary link above points to its entry. Library/framework glossary lives separately in [`ombuds_build_glossary.md`](ombuds_build_glossary.md).

## Notion sync pending

- 2026-09-25: "Call OpenAI & Anthropic APIs directly, compare outputs" marked done here. No Notion connector was available in that session to update the board itself — mark it done on the Notion page manually, or re-run the sync from a session with Notion access. See the "Done, W1: provider comparison" note below for what to paste into the page.
