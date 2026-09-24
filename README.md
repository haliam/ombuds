# Ombuds — agentic claims-triage system


**An agentic claims-triage system — built to demonstrate production-grade AI engineering, not just an LLM demo.**

Ombuds is a support/claims-triage capstone project built as a 4-week hands-on prep exercise for an AI & Agentic Engineer (Forward Deployed Engineer) role. Its purpose is to prove — with real, running, testable code — the full set of skills that role requires: LLM fundamentals, agentic orchestration, RAG, MCP-based tool exposure, human-in-the-loop governance, and production observability.

## What it does

A claim comes in — for example, a flight cancellation compensation claim. Ombuds:

1. **Classifies** it (category, urgency, confidence) using structured, schema-validated LLM output — never free-text parsing.
2. **Retrieves precedent** via RAG — similar past claims and relevant policy documents, cited, not invented.
3. **Checks eligibility** against a deterministic rules engine (e.g. EU261 compensation tiers) — the LLM can *ask* for this fact, it can never *decide* it.
4. **Decides** what to recommend: log the claim, and/or propose a payout or escalation.
5. **Gates risky actions behind a human.** Low-risk actions (logging) auto-execute. Any state-changing, money-moving, or access-granting action is hard-blocked by policy and requires human approval — regardless of how confident the model is.
6. **Executes only after approval**, through tools exposed over MCP (Model Context Protocol), writing to a deterministic Postgres backend that the LLM never owns.
7. **Logs everything** — every LLM call, every tool call, every human decision — as a trace and an audit record.

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
Ticket in → classify (LLM, structured output)
         → retrieve similar past claims + policy docs (RAG, cited)
         → check_eligibility (deterministic tool, via MCP)
         → decide: propose action(s)
         → guardrail: low-risk auto-runs / high-risk requires human approval
         → [approved] → act (MCP tool, writes to Postgres)
         → every step traced + audited
```

Full breakdown in [`docs/architecture.md`](docs/architecture.md) and the design decisions behind it in [`docs/decisions/`](docs/decisions/).

## What this project is not

- Not autonomous — no state-changing action fires without a human or a hard policy check approving it.
- Not a UI product — API + agent + demo script only.
- Not integrated with a real airline/claims vendor — tools are mocked against a local Postgres, proving the *pattern* (agent → MCP → deterministic backend), not a vendor integration.
- Not multi-agent — one LangGraph agent, one tool set.

## Status: Week scaffold

Project structure is in place; implementation follows the 4-week build plan below.

| Week | Focus |
|---|---|
| 1 | Raw LLM API calls, tool-calling loop, structured output, `/triage` endpoint, tests |
| 2 | LangGraph agent, MCP server, agent memory, human-approval gate |
| 3 | RAG pipeline, Postgres + vector store, Docker Compose, PII/injection guardrails |
| 4 | Observability (OpenTelemetry), OPA/Rego policy, audit trail, architecture docs |

## Stack

FastAPI · LangGraph · MCP · Anthropic/OpenAI APIs · PostgreSQL + pgvector/Chroma · Docker Compose · OpenTelemetry · OPA/Rego
