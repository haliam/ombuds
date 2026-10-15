# Ombuds — agentic claims-triage system


**An agentic claims-triage system — built to demonstrate production-grade AI engineering, not just an LLM demo.**

Ombuds is a support/claims-triage capstone project built as a 4-week hands-on prep exercise for an AI & Agentic Engineer (Forward Deployed Engineer) role. Its purpose is to prove — with real, running, testable code — the full set of skills that role requires: LLM fundamentals, agentic orchestration, RAG, MCP-based tool exposure, human-in-the-loop governance, and production observability.

## What it does

A claim comes in — for example, a flight cancellation compensation claim. Ombuds:

1. **Reads** it with an LLM that either asks the passenger a clarifying question or returns a structured, schema-validated verdict — never free-text parsing.
2. **Retrieves policy** via RAG (`search_kb`) — relevant policy documents from pgvector, cited, not invented.
3. **Checks eligibility** against a deterministic rules engine (e.g. EU261 compensation tiers) — the LLM can *ask* for this fact, it can never *decide* it.
4. **Decides** what to recommend: the verdict is re-checked against the rules engine, repaired or escalated to a human if it disagrees, and the claim is submitted for logging.
5. **Gates risky actions behind a human.** Every state-changing action (`log_claim` today; `issue_payment`, which the agent is never offered) only *submits* an approval request and waits for a human, regardless of how confident the model is. The W4 OPA/Rego policy will let low-risk logging auto-execute and always require a human for money.
6. **Executes only after approval.** A state-changing tool call (made directly or over MCP, the Model Context Protocol) only *submits* the exact rules-derived action; once a human approves it, that action executes exactly once against Postgres, which the LLM never owns ([ADR-0009](docs/decisions/0009-approval-request-is-the-pending-action.md)): `log_claim` writes the `claims` row, and `issue_payment` writes a *simulated* payout record to `payments` (there is no real payment rail) and requires a logged claim with a matching amount.
7. **Guards its inputs.** Claim text is screened for prompt injection and redacted for PII before the model sees it. *Planned for W4:* a trace and audit record of every LLM call, tool call and human decision.

## The core architectural claim

> **The LLM decides *how* to investigate a claim. It never becomes the source of truth for the claim's outcome.**

A tool being *callable* by the agent must never imply automatic *permission* to execute the underlying action. That boundary — enforced in code and policy, not just prompted for — is the single idea this whole project is built to demonstrate.

## Why airline claims (EU261)

Flight cancellation/delay compensation was chosen as the first concrete vertical because it needs no contrived complexity to justify every piece of the architecture:

- Compensation eligibility is a real, checkable, deterministic rule set (distance tiers, notice period, exemption reasons) — a natural fit for a tool the LLM calls but doesn't compute itself.
- A payout is real money — nobody needs convincing that it should require human approval.
- Past claims and policy documents give RAG genuine work to do, not decorative retrieval.

The architecture is deliberately domain-agnostic underneath: `features/claims_triage/` doesn't know it's handling flights. A second vertical (e.g. bus or rail delay claims) would mean adding one rules module and one evidence schema — zero changes to the agent, the guardrails, or the approval flow. Only one vertical (airline) is built in this 4-week scope; the plug-in seam is structural, not yet exercised by a second implementation.

## Architecture at a glance

```
Claim in → injection screen + PII redaction
         → LangGraph tool loop: search_kb (RAG, cited) / check_eligibility (deterministic rules) / log_claim
         → verify the verdict against the rules engine (repair, else escalate to a human)
         → state-changing tool calls only submit an approval request (Postgres)
         → [human approves] → execute the approved action exactly once (writes to Postgres)
         → W4: every step traced + audited, OPA/Rego payout policy
```

Full breakdown in [`docs/architecture.md`](docs/architecture.md) and the design decisions behind it in [`docs/decisions/`](docs/decisions/).

## What this project is not

- Not autonomous — no state-changing action fires without a human or a hard policy check approving it.
- Not a UI product — API + agent + demo script only.
- Not integrated with a real airline/claims vendor — tools are mocked against a local Postgres, proving the *pattern* (agent → MCP → deterministic backend), not a vendor integration.
- Not multi-agent — one LangGraph agent, one tool set.

## Status: Weeks 1–3 built, pre-W4 refactor done

The agent, RAG, Postgres-backed approvals and execution, MCP server, Docker Compose stack and PII/injection guardrails work; observability, the OPA policy and the audit trail (Week 4) are not built yet. Run it with `make up` (needs `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `.env`).

| Week | Focus |
|---|---|
| 1 | Raw LLM API calls, tool-calling loop, structured output, `/triage` endpoint, tests |
| 2 | LangGraph agent, MCP server, agent memory, human-approval gate |
| 3 | RAG pipeline, Postgres + vector store, Docker Compose, PII/injection guardrails |
| 4 | Observability (OpenTelemetry), OPA/Rego policy, audit trail, architecture docs |

## Stack

FastAPI · LangGraph · MCP · Anthropic/OpenAI APIs · PostgreSQL + pgvector/Chroma · Docker Compose · OpenTelemetry · OPA/Rego
