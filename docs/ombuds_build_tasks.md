# ombuds — Build Task List

Extracted from the "🤖 AI Build" view of the AI Interview Notion database (snapshot — re-extract if the Notion board has moved on since this was pulled).

Legend: [x] Done · [~] Learning/in progress · [ ] Not started. Priority shown as 🔴 High / 🟡 Medium / 🟢 Low.

## Week 1 — Raw API Fundamentals + Engineering Foundation

- [x] Design the folder structure to the project — 🔴 High
- [~] Call OpenAI & Anthropic APIs directly, compare outputs — 🟡 Medium
- [ ] Define tool schemas (`create_ticket`, `check_sla`) + parse tool-use loop — 🔴 High
- [ ] Build FastAPI `/triage` endpoint (raw SDK, no framework) — 🔴 High
- [ ] Write unit tests for tool-calling parser + endpoint — 🟡 Medium
- [ ] Implement streaming (SSE) + buffered JSON parsing — 🟡 Medium
- [ ] Add structured output validation with Pydantic + retry/repair — 🔴 High
- [ ] Add retries/backoff, timeouts, fallback model, idempotency — 🔴 High

## Week 2 — Agentic Loop + MCP

- [ ] Rebuild tool-calling loop in LangGraph — 🔴 High
- [ ] Stand up MCP server (`search_kb`, `check_sla`, `create_ticket`, `escalate_ticket`) — 🔴 High
- [ ] Connect LangGraph agent to tools over MCP — 🔴 High
- [ ] Add short-term + long-term memory to agent state — 🟡 Medium
- [ ] Add escalation/retry loop on low confidence — 🟡 Medium
- [ ] Add human-approval gate before state-changing tool calls — 🔴 High

## Week 3 — RAG, Data Layer, Docker, Guardrails

- [ ] Set up Postgres (relational) + pgvector/Chroma (embeddings) — 🔴 High
- [ ] Build RAG pipeline — chunk → embed → store → retrieve → cite — 🔴 High
- [ ] Build small eval set (20–30 Q/A pairs), measure retrieval quality — 🟡 Medium
- [ ] Write Docker Compose for full stack, verify `docker compose up` — 🔴 High
- [ ] Add PII filtering on inputs/outputs — 🟡 Medium
- [ ] Add prompt-injection test cases — 🔴 High
- [ ] Write integration test for `/triage` end-to-end — 🟡 Medium

## Week 4 — Observability, Governance, Polish

- [ ] Write one OPA/Rego policy (block auto-escalate above priority X) — 🔴 High
- [ ] Build audit trail — log every tool call + decision — 🟡 Medium
- [ ] Write architecture diagram + README (problem, design, trade-offs) — 🔴 High

---

Note: there's a gap in the Notion ordering between "integration test for `/triage`" (W3) and "OPA/Rego policy" (W4) — one task (likely OpenTelemetry tracing, per the roadmap's week 4 plan) doesn't currently have a row in this view. Worth checking the board directly in case it exists elsewhere or was dropped.
