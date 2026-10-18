# ADR-0015: OPA server sidecar for payout policy, denying at submit and failing closed

**Status:** accepted
**Date:** 2026-10-18

## Context
AGENTS.md requires every state-changing tool to be checked against a policy engine, and the W4 plan calls for one Rego policy: block payouts above EUR X. `policy_engine.py` and `payout_approval.rego` were empty scaffolds. ADR-0009 already says a money-moving action always needs a human, so the policy is not a replacement for approval. It is a ceiling above which the automated path refuses to even ask.

Open choices: how Rego is evaluated, what a denial means, and where the check sits.

## Decision
- **Evaluation:** an OPA server (`openpolicyagent/opa`, the `opa` service in `docker-compose.yml`) loads `platform/guardrails/policies/*.rego` (tests excluded). `OpaHttpPolicyEngine` POSTs the input to `v1/data/ombuds/payout/decision` with the standard library, so there is no new Python dependency. It sits behind a `PolicyEngine` protocol that the composition roots inject.
- **Where:** `PolicyCheckedApprovalStore` decorates the runtime store (outermost, around `ExecutingApprovalStore`) and evaluates on `submit`. Every state-changing tool, in-process or over MCP, goes through it, and `build_runtime` requires the engine and the limit, so a root can't omit the guardrail.
- **Input is server-side only:** `action`, the rules-derived `payload` (including `amount_eur`) and `limits.max_payout_eur`. The limit comes from config (`PAYOUT_LIMIT_EUR`, default 400, which blocks the EUR 600 tier). Nothing the model authored is trusted (ADR-0009).
- **A denial creates no approval request.** It raises `PolicyDeniedError` (a `ToolExecutionError`) with reason codes (`payout_above_limit`, `payout_amount_invalid`, `payout_limit_missing`), so a human cannot approve an over-limit payout from the queue.
- **Fail closed:** if OPA is unreachable, times out, or returns no well-formed decision, the engine denies with `policy_unavailable`. Missing or non-numeric amounts and a missing limit are also denials inside the Rego.
- The decision document carries `policy_version`, which the audit trail (next W4 task) will record.

## Consequences
- Easier: the rule is declarative, reviewable and testable on its own (`make test-policy` runs `opa check --strict` and the Rego tests in the container). Changing the limit is configuration, not code.
- Easier: the Python side stays small and fakeable; unit tests use a fake engine and a stubbed HTTP call.
- Harder: one more service in the stack. If OPA is down, all state-changing submissions are denied (including `log_claim`), which is the safe direction but an availability cost.
- Not covered: policy runs at submit, not again at approve, so lowering the limit does not cancel requests already pending. `log_claim` is allowed by the current policy and still needs a human; the ADR-0009 end state of auto-executing it is not part of this change.

## Alternatives considered
- **Embedded evaluation** (a Rego engine inside the Python process, e.g. `regorus`): no extra service, but no maintained Python package was installable here, and it would tie us to a smaller engine than OPA itself.
- **OPA as a Wasm module or CLI per call:** process or runtime overhead per check, and more moving parts than an HTTP call.
- **The rule in Python:** simplest, but it is the thing AGENTS.md asks to keep as policy-as-code, and it would sit with the business rules rather than the governance layer.
- **Escalate instead of deny above the limit:** the payment would still be approvable by whoever sees the queue. Revisit if the business wants a second, senior approval path.
