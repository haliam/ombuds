# Triage and Approval Flow

**Version** 1.0 · **Date** 2026-10-18 · **Tool** archify · **Type** sequence · **Pinned commit** `7342b6c`
**Decisions** [ADR-0009](../decisions/0009-approval-request-is-the-pending-action.md), [ADR-0014](../decisions/0014-heuristic-injection-detection-escalates.md)
**Source** `triage_use_case.py`, `agent/graph.py`, `platform/guardrails/approval_gate.py`, `executing_store.py`

![triage-approval-flow](archify/triage-approval-flow.png)

Interactive version: [`archify/triage-approval-flow.html`](archify/triage-approval-flow.html) · Source: [`archify/triage-approval-flow.json`](archify/triage-approval-flow.json)

## What it shows

One triage and the later human approval as two separate moments. The agent only submits `log_claim`; only after a human approves does the executor write to Postgres. A suspected injection, a verdict that still disagrees with the rules engine after two repairs, or more than eight tool turns all end in an escalation instead of a verdict.

## Like I'm 5

Think of ordering something from a shop with a parent. You tell the shop what you want. The shop checks your message for tricks and covers up private things like your address. A helper reads it, looks up the rules, and writes a form that says "this child may get a refund of this much". But the form is only a request. It goes into a tray. Later, a grown-up looks at the tray, reads the form, and signs it. Only after the signature does anything happen, and it happens exactly one time. Until then, nothing has changed anywhere.

## For an interviewer

This sequence shows one triage and then the later approval, which are two separate moments. In the first, the API screens the claim for prompt injection and redacts personal data, then the agent loop runs. The only state-changing tool the agent has, log_claim, does not write anything. It submits a payload-bound approval request. The payload is derived from the rules engine, never from model text, and the claim identifier is issued by the server, so the model cannot choose it. In the second moment, a human calls the approvals API. Approving runs an executor registered for that action, which writes to Postgres, and the request moves to executed exactly once. This is the decision in ADR-0009. The alternative, a LangGraph interrupt with a checkpointer, ties approvals to graph checkpoints and does not cover external MCP clients, so it was rejected for now. The cost is that the agent cannot tell the passenger the final outcome in the same run. Honest gap: until the Rego policy exists, log_claim also needs a human, though the target is to auto-approve it by policy.

## Likely follow-up

What if the executor fails after approval? The request stays approved, the write is idempotent, and execute_approved can be re-run safely, although nothing calls it automatically yet.

## Regenerate

Edit [`archify/triage-approval-flow.json`](archify/triage-approval-flow.json) (bump the version and date in `meta.title`), then from the repo root:

```bash
python docs/diagrams/src/render_archify.py triage-approval-flow
```

This runs `archify finalize sequence` and rewrites the `.html` and `.png` next to the JSON. The HTML stays under the repo's 1000 KB `check-added-large-files` limit.

## Change log

- 1.0 (2026-10-18): first versioned release; title, version and date added to the diagram itself.
