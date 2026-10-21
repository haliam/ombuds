# Ombuds Claims Triage

**Version** 1.1 · **Date** 2026-10-21 · **Tool** archify · **Type** component · **Pinned commit** `8a6776c`
**Decisions** [ADR-0001](../../decisions/0001-langgraph-over-crewai.md), [ADR-0002](../../decisions/0002-feature-sliced-over-clean-layers.md), [ADR-0009](../../decisions/0009-approval-request-is-the-pending-action.md), [ADR-0015](../../decisions/0015-opa-sidecar-over-embedded-evaluation.md), [ADR-0016](../../decisions/0016-append-only-postgres-audit-log-at-the-governance-seams.md), [ADR-0017](../../decisions/0017-opentelemetry-spans-at-the-existing-seams.md)
**Source** `src/ombuds/api_app.py`, `features/claims_triage/`, `platform/` (source lines are cited per component in the JSON)

![architecture](architecture.png)

Interactive version: [`architecture.html`](architecture.html) · Source: [`architecture.json`](architecture.json)

## What it shows

The components of one triage and how they connect: claim in over HTTP, guardrails in front of the agent, tools behind a scoped dispatcher, and every state change going through the policy check and the approval gate to Postgres, with an audit log and spans at the seams.

## Like I'm 5

Imagine a post office. A person hands over a letter asking for help with a cancelled flight. A friendly clerk reads it and asks a very smart helper what to do. The helper is allowed to look things up in a big book of rules and to use a calculator, but the helper is never allowed to give out money. If something needs money or a stamp, the clerk writes a note and puts it in a box. Only the boss, a real person, can open the box and say yes or no. Everything is written down in one big notebook that everybody shares, so nothing gets lost.

## For an interviewer

Ombuds triages EU261 airline compensation claims. A FastAPI app receives a claim and a use case runs a LangGraph agent. The agent calls an LLM, which can only use three tools: search the policy knowledge base, check eligibility with a deterministic rules engine, and log a claim. The model asks for eligibility, it never decides it. Anything that changes state does not execute inline. It submits an approval request, and a human approves it before the action runs. Postgres with pgvector holds claims, payments, approvals and the knowledge base embeddings, so there is one database to operate. Code is feature-sliced: claims-specific code is separate from a feature-agnostic platform layer (LLM providers, guardrails, MCP, infrastructure), and only the composition roots wire them together. The trade-off is more structure than a prototype needs, for a cheap second vertical. The Week 4 pieces are built: an OPA/Rego payout cap that fails closed when the approval is submitted, an append-only audit log, and OpenTelemetry spans. Honest gap: no end-to-end agent eval yet, only retrieval is measured.

## Likely follow-up

Why not let the LLM decide eligibility? Because it is a legal calculation with exact tiers, so a deterministic engine is auditable and the model's answer is checked against it.

## Regenerate

Edit [`architecture.json`](architecture.json) (bump the version and date in `meta.title`), then from the repo root:

```bash
python docs/diagrams/render_archify.py architecture
```

This runs `archify finalize architecture` and rewrites the `.html` and `.png` next to the JSON. The HTML stays under the repo's 1000 KB `check-added-large-files` limit.

## Change log

- 1.0 (2026-10-18): first versioned release; title, version and date added to the diagram itself.
- 1.1 (2026-10-21): Week 4 pieces drawn as built (OPA policy engine, audit log, OpenTelemetry spans) instead of "planned"; re-pinned to `8a6776c`.
