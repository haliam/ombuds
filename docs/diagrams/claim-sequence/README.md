# Claim Run Sequence

**Version** 1.0 · **Date** 2026-10-19 · **Tool** archify · **Type** sequence · **Pinned commit** `38ea673`
**Decisions** [ADR-0009](../../decisions/0009-approval-request-is-the-pending-action.md), [ADR-0012](../../decisions/0012-retrieval-relevance-floor.md), [ADR-0014](../../decisions/0014-heuristic-injection-detection-escalates.md), [ADR-0015](../../decisions/0015-opa-sidecar-over-embedded-evaluation.md)
**Source** `triage_use_case.py`, `agent/graph.py`, `tools/`, `rag/retriever.py`, `platform/guardrails/policy_checked_store.py`, `executing_store.py`, `api.py`

![claim-sequence](claim-sequence.png)

Interactive version: [`claim-sequence.html`](claim-sequence.html) · Source: [`claim-sequence.json`](claim-sequence.json)

## What it shows

One airline claim from the POST to the executed payment, in three groups: intake and the tool loop, the verified verdict and the pending approval, and the later human approval. It is the whole run in order. [Triage and Approval Flow](../triage-approval-flow/README.md) covers only the submit and approve moments.

## Like I'm 5

You hand a form to a clerk. The clerk checks it for tricks and hides your private details, then asks a helper. The helper looks in the rule book, asks a calculator for the sum and writes an answer. A checker makes sure the answer matches the calculator. The answer only becomes a request in a tray. Later a boss signs it, and only then does anything change, exactly once.

## For an interviewer

The order is the point. Guards run before any model call. The model plans tool calls, the rules code returns the amount and the retriever returns cited chunks above a 0.35 floor. The model's verdict is verified against the rules, with two repairs before an escalation. `log_claim` goes to OPA and, if allowed, submits a pending request with a server-issued claim id, so the model never chooses it. Approval is a separate request: the approvals API approves, the executor writes the claim once, and every step writes an audit row and a span. Trade-off: the agent cannot tell the claimant the final outcome in the same run. Gaps: memory needs a claimant id, MCP and the escalation branches are not drawn, and some notes are shortened to fit.

## Likely follow-up

What if OPA denies? No approval request is created, so a human cannot approve it from the queue.

## Regenerate

`python docs/diagrams/render_archify.py claim-sequence` after editing the JSON (bump the version and date in `meta.title`).

## Change log

- 1.0 (2026-10-19): first versioned release.
