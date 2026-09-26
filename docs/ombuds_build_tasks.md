# ombuds — Build Task List

Extracted from the "🤖 AI Build" view of the AI Interview Notion database (snapshot — re-extract if the Notion board has moved on since this was pulled).

Legend: [x] Done · [~] Learning/in progress · [ ] Not started. Priority shown as 🔴 High / 🟡 Medium / 🟢 Low.

## Week 1 — Raw API Fundamentals + Engineering Foundation

- [x] Design the folder structure to the project — 🔴 High
- [x] Implement EU261 rules engine (`verticals/airline/rules.py`) + unit tests — 🔴 High — [summary](ombuds_build_task_summaries.md#implement-eu261-rules-engine-verticalsairlinerulespy--unit-tests)
- [x] Call OpenAI & Anthropic APIs directly, compare outputs — 🟡 Medium — [summary](ombuds_build_task_summaries.md#call-openai--anthropic-apis-directly-compare-outputs)
- [x] Stub `approval_gate` as deny-all before any state-changing tool is registered — 🔴 High — [summary](ombuds_build_task_summaries.md#stub-approval_gate-as-deny-all-before-any-state-changing-tool-is-registered)
- [x] Define tool schemas (`check_eligibility`, `log_claim`) + parse tool-use loop — 🔴 High — [summary](ombuds_build_task_summaries.md#define-tool-schemas-check_eligibility-log_claim--parse-tool-use-loop)
- [x] Build FastAPI `/triage` endpoint (raw SDK, no framework) — 🔴 High — [summary](ombuds_build_task_summaries.md#build-fastapi-triage-endpoint-raw-sdk-no-framework)
- [x] Write unit tests for tool-calling parser + endpoint — 🟡 Medium — [summary](ombuds_build_task_summaries.md#write-unit-tests-for-tool-calling-parser--endpoint)
- [x] Implement streaming (SSE) + buffered JSON parsing — 🟡 Medium — [summary](ombuds_build_task_summaries.md#implement-streaming-sse--buffered-json-parsing)
- [ ] Add structured output validation with Pydantic + retry/repair — 🔴 High
- [ ] Add retries/backoff, timeouts, fallback model, idempotency — 🔴 High

## Week 2 — Agentic Loop + MCP

- [ ] Rebuild tool-calling loop in LangGraph — 🔴 High
- [ ] Stand up MCP server (`search_kb`, `check_eligibility`, `log_claim`, `issue_payment`) — 🔴 High
- [ ] Connect LangGraph agent to tools over MCP — 🔴 High
- [ ] Add short-term + long-term memory to agent state — 🟡 Medium
- [ ] Add escalation/retry loop on low confidence — 🟡 Medium
- [ ] Replace deny-all stub with human-approval gate before state-changing tool calls — 🔴 High

## Week 3 — RAG, Data Layer, Docker, Guardrails

- [ ] Set up Postgres (relational) + pgvector/Chroma (embeddings) — 🔴 High
- [ ] Build RAG pipeline — chunk → embed → store → retrieve → cite — 🔴 High
- [ ] Build small eval set (20–30 Q/A pairs), measure retrieval quality — 🟡 Medium
- [ ] Write Docker Compose for full stack, verify `docker compose up` — 🔴 High
- [ ] Add PII filtering on inputs/outputs — 🟡 Medium
- [ ] Add prompt-injection test cases — 🔴 High
- [ ] Write integration test for `/triage` end-to-end — 🟡 Medium

## Week 4 — Observability, Governance, Polish

- [ ] Add OpenTelemetry tracing (span per LLM/tool call) — 🟡 Medium
- [ ] Write one OPA/Rego policy (block auto-payout above €X) — 🔴 High
- [ ] Build audit trail — log every tool call + decision — 🟡 Medium
- [ ] Write architecture diagram + README (problem, design, trade-offs) — 🔴 High

---

Tool names follow ADR-0004 (EU261 tool set, not generic helpdesk tools). Last synced with Notion 2026-09-24.

Per-task recaps (goal, files touched, libraries used) live in [`ombuds_build_task_summaries.md`](ombuds_build_task_summaries.md) — each `[x]` item above links to its entry. Library/framework glossary lives separately in [`ombuds_build_glossary.md`](ombuds_build_glossary.md).

## Notion sync pending

- 2026-09-25: "Call OpenAI & Anthropic APIs directly, compare outputs" marked `[x]` here. No Notion connector was available in that session to update the board itself — mark it done on the Notion page manually, or re-run the sync from a session with Notion access. See the "Done, W1: provider comparison" note below for what to paste into the page.
