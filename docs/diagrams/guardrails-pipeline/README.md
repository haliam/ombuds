# Guardrails and Tool Scoping Pipeline

**Version** 1.1 · **Date** 2026-10-22 · **Tool** archify · **Type** dataflow · **Pinned commit** `cbc2790`
**Decisions** [ADR-0013](../../decisions/0013-regex-pii-redaction-at-the-trust-boundaries.md), [ADR-0014](../../decisions/0014-heuristic-injection-detection-escalates.md), [ADR-0015](../../decisions/0015-opa-sidecar-over-embedded-evaluation.md)
**Source** `platform/guardrails/` (`injection_detection.py`, `pii_filter.py`, `guarded_dispatcher.py`, `approval_gate.py`), `features/claims_triage/tools/`

![guardrails-pipeline](guardrails-pipeline.png)

Source: [`guardrails-pipeline.json`](guardrails-pipeline.json)

## What it shows

Where untrusted text is screened and redacted, and where the model's authority ends: it never chooses the `claim_id`, is never offered `issue_payment`, and `log_claim` only submits a rules-derived approval request.

## Like I'm 5

Picture a mailroom in front of a very clever robot. Before any letter reaches the robot, a guard checks whether the letter is secretly bossing the robot around, like "forget your rules". If it is, the letter goes straight to a person and the robot never sees it. Then someone paints over private things such as phone numbers and bank numbers. The robot also only gets three tools in its toolbox, and the dangerous one, paying money, is locked away. The robot can ask for things, but the grown-up rules decide what really happens.

## For an interviewer

Governance is layered, and each layer assumes the one before it can fail. First, a heuristic injection detector screens the claim, and a hit returns an escalated result with no model call at all (ADR-0014). Second, PII is redacted before the model sees the text, again in tool-call arguments through a guarded dispatcher, and again in the answer, explanation and escalation reason (ADR-0013). Third, tool scoping offers the agent only search_kb, check_eligibility and log_claim, and overwrites any claim identifier the model supplies with the server-issued one. issue_payment is never offered to the agent. Fourth, log_claim recomputes eligibility with the rules engine and only submits an approval request. The point is that the model's authority ends at the tool boundary. Trade-offs: regex detection will miss paraphrases and unseen languages, and PII redaction is pattern-based. Fifth, an OPA/Rego policy is checked when the request is submitted and refuses a payout above the cap, and it denies if OPA is unreachable (ADR-0015). Honest gap: tool results are not filtered.

## Likely follow-up

If injection detection is bypassed, what is the blast radius? Small, because the model has no payment tool, cannot pick the claim id, and any action still needs a human approval.

## Regenerate

Edit [`guardrails-pipeline.json`](guardrails-pipeline.json) (bump the version and date in `meta.title`), then from the repo root:

```bash
python docs/diagrams/render_archify.py guardrails-pipeline
```

This runs `archify finalize dataflow` and rewrites the `.png` next to the JSON.

## Change log

- 1.0 (2026-10-18): first versioned release; title, version and date added to the diagram itself.
- 1.1 (2026-10-22): the OPA payout policy is drawn as built (it was listed as "not built yet").
