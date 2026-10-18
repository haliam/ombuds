# How to work: build a slice, then explain it

Pair each build task with the interview question it answers. For every pair:

1. **Read first (about 30 min).** Read just enough to understand the concept. Don't read the framework docs cover to cover.
2. **Build it by hand.** Write the core logic yourself. Use me to review your code or explain an error, not to write the main piece. You can't explain in an interview a loop you've never debugged.
3. **Test it.** Write the test in the same commit. That's already a project rule in `AGENTS.md`.
4. **Explain it.** Write the answer to the paired question in its Notion page. Base it on your own code: "in ombuds I did X because Y, and the trade-off is Z." Aim for a 2-minute spoken answer.
5. **Record decisions.** When you choose between real options (retry strategy, pgvector or Chroma, where the approval gate goes), write a short ADR. These become your talking points in interviews.

Every week then leaves you with working code plus answers you've practised. This is the method for the whole 4-week build — the table below tracks how it played out for W1 and W2 specifically, and stays the plan for W3–4.

## How the tasks pair up

| Week | Build | Question to answer after |
| --- | --- | --- |
| **1** | EU261 rules engine (`verticals/airline/rules.py`) | Foundation for **Q5 callable ≠ permitted** — rules, not the LLM, decide eligibility |
|  | Call the APIs directly, compare outputs | Q18 cost and latency |
|  | Tool schemas and tool-use loop | **Q3 the tool-calling loop** |
|  | Pydantic output validation, retry/repair | **Q19 structured output vs prompted JSON** (ADR-0005) |
|  | Retries, backoff, fallback model, idempotency | Q20 provider outage (ADR-0006) |
|  | `/triage` endpoint, streaming, tests | Q17 SSE vs WebSockets (ADR-0007) |
| **2** | Rebuild the loop in LangGraph | **Q2 agent vs workflow**, framework comparison notes (ADR-0001) |
|  | MCP server, and connect the agent to it over MCP | **Q4 MCP** (ADR-0003) |
|  | Human-approval gate | **Q5 callable ≠ permitted**, Q21 human-in-the-loop placement (ADR-0008, ADR-0009) |
|  | Memory, escalate/retry on low confidence | Q22 memory, Q23 multi-agent |
| **3** | Postgres + pgvector, RAG pipeline | **Q7 RAG walkthrough**, Q12 Neo4j vs Postgres |
|  | Eval set (20–30 pairs) | **Q8 evaluation** |
|  | PII filter, prompt-injection tests | **Q10 governance**, Q11 injection |
|  | Docker Compose, integration test | Q24 containerizing an agent app |
| **4** | OpenTelemetry, Rego policy, audit trail, README | System-design rehearsal for this project, red-team list, demo script |
|  | Mock interviews, STAR stories | These are prep only, with nothing to build. Start them in week 3, not week 4. |

The full per-task checklist and status lives in [`progress/tasks.md`](progress/tasks.md); per-task build notes in [`progress/task_summaries.md`](progress/task_summaries.md).

## W1 → W2: what shipped, and where it diverged from the original plan

Four gaps existed between this plan and the Notion board when the build started. All four are resolved; recorded here so the reasoning isn't lost.

1. **Tool names.** Notion originally listed generic helpdesk tools (`create_ticket`, `check_sla`, `escalate_ticket`). The build used the EU261-specific set instead — `search_kb`, `check_eligibility`, `log_claim`, `issue_payment` — because a claims-triage demo needs claims-shaped tools to be legible in an interview. Recorded as ADR-0004.
2. **Rules engine had no task.** Added as the first W1 task, ahead of anything LLM-related: `verticals/airline/rules.py` (distance tiers, notice periods, exemptions) plus unit tests. Pure Python, no LLM — it's the ground truth `check_eligibility` calls into, and the reason the agent can't talk its way past an ineligible claim.
3. **OpenTelemetry task location.** Was filed under the Training view instead of Build; moved to W4 Build, where the tracing work actually happens.
4. **Approval gate sequencing.** The gate was originally scheduled for W2, but `issue_payment` (a state-changing tool) existed from W1. Rather than pull the whole gate forward, W1 shipped `approval_gate` as a **deny-all stub** so no state-changing tool could execute before real governance existed — then W2 replaced the stub with the actual human-approval flow (ADR-0008), later hardened into a submit-once/execute-once model after a W1 review flagged that a retried approval could double-pay a claim (ADR-0009, `docs/reviews/w1_review_pre_w2_plan.md` finding F-04). That boundary — a tool being *callable* is not the same as being *permitted* — is the throughline for Q5 and the main claim in the README.

The README's leftover chat-text artifact from the original draft was also cleaned up as part of this pass.

## What was built in W1 and W2

- **Raw loop (W1):** direct Anthropic/OpenAI calls, hand-rolled tool-use loop, Pydantic-validated structured output with repair-on-failure, two-layer resilience (retry/backoff + fallback model), `/triage` over FastAPI with SSE streaming.
- **Agentic loop (W2):** the same responsibilities rebuilt as a LangGraph graph (`agent/graph.py` and `agent/nodes/escalate_retry.py`; classify, retrieve and decide happen inside the model's tool loop, and the unused stubs were deleted) — `/triage` and `/triage/stream` now run the same graph rather than two parallel implementations, decided as an amendment to ADR-0007.
- **MCP (W2):** `platform/mcp/server.py` builds a `ToolRegistry` from `claims_triage.tools.build_tool_registry()` and exposes it over `tool_bindings.py`, so the same tools are callable directly or via MCP without duplicating dispatch logic (ADR-0003).
- **Memory (W2):** short-term and long-term memory under `agent/memory/`, added to the model's system prompt by `agent/graph.py`. Escalation on low confidence is a separate node, `escalate_retry.py`.
- **Governance (W2):** `platform/guardrails/approval_gate.py` sits in front of `log_claim` and `issue_payment`. (`policy_engine.py` is still an empty stub; the OPA policy is a W4 task.) Per ADR-0009, a tool call only *submits* a payload-bound approval request with server-issued `claim_id` and rules-derived amounts — never model-authored ones — and execution happens exactly once, after a human approves, never inline in the tool.

A fuller review of what W2 changed architecturally, plus the hardening work done before W3 started, is in [`reviews/w2_review_pre_w3_plan.md`](progress/w2_review_pre_w3_plan.md).

## W3 and the pre-W4 refactor: what shipped

- **W3:** Postgres + pgvector (ADR-0010), the RAG pipeline (ADR-0011), the retrieval eval and relevance floor (ADR-0012), PII redaction (ADR-0013), prompt-injection detection (ADR-0014), Docker Compose, and an end-to-end `/triage` integration test.
- **Pre-W4 refactor (from [`reviews/w3_review_pre_w4_plan.md`](progress/w3_review_pre_w4_plan.md)):** the approval store, pool and tool registry are injected at the composition roots; an approved request now runs its executor exactly once and writes `claims` and `payments` rows; `run_triage` and `stream_triage` share one setup step; the docs were reconciled.
- Of the decisions the plan said to record, pgvector vs Chroma was the first one due, and it is ADR-0010.

## Next: W4

Remaining tasks: OpenTelemetry tracing, one OPA/Rego payout policy, and the audit trail (the architecture diagram + README task is done). Same method as before: read just enough, build the core logic by hand, test in the same commit, write the paired Notion answer, and record any real decision as an ADR. Status lives in [`progress/tasks.md`](progress/tasks.md).
