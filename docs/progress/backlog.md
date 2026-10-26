# Backlog — open items from the W1–W3 reviews

The three stage reviews (`w1_review_pre_w2_plan.md`, `w2_review_pre_w3_plan.md`, `w3_review_pre_w4_plan.md`) were deleted once every required task (T-*, P-*) was done. They stay in git history. These optional findings were still open in the code on 2026-10-18.

| Item | Origin | Status in code |
|---|---|---|
| Auth on `/approvals/*`, with `approver` derived from the token | W3 F-03, W2 F-13 | No token check; `approver` is self-declared, so audit rows record an unverified actor |
| CI (lint + unit; integration with a pgvector service) | W3 F-10, W2 O-4 | No `.github/workflows` |
| Frozen settings object instead of import-time env reads | W3 F-09 | Still module-level in `config.py`; W4 added more settings |

Not re-verified: small W1/W2 hygiene items (`McpToolClient` enter leak, `FallbackProvider` docstring).

## Added from `/codebase-review W4 W5` (2026-10-18)

Full detail in the first W4 review (git history, `360b5c5`). The four required pre-W5 tasks (P-1 to P-4: approval recovery route, loopback ports and OPA exposure, `/approvals` auth, docs reconciliation) are tracked there, not here. The optional items are:

| Item | Origin | Status in code |
|---|---|---|
| ~~Agent-level eval dataset and runner~~ | W4 O-1 (W3 F-07) | Done in W6: `make eval-agent` |
| ~~Explicit `env` for the MCP subprocess~~ | W4 F-05 | Done: `McpToolClient` passes the full parent environment (de00717), so `DATABASE_URL`, `OPA_*`, `PAYOUT_LIMIT_EUR` and `OTEL_*` reach the child; no explicit allowlist needed |
| ~~Audit the out-of-scope tool call and the injection escalation; span the approvals routes; fix the "must not proceed unaudited" docstring~~ | W4 F-06 | Done in W6 (migration 0004, ADR-0016 amended) |
| Add an OPA healthcheck (the scalar pin is done) | W4 F-08 | `api` waits for OPA only with `service_started` |

## Added from `/codebase-review W4 W5` second pass (2026-10-21)

Full detail in [`w4_review_pre_w5_plan_rev2.md`](w4_review_pre_w5_plan_rev2.md). Design notes for the W5 tasks are in `tasks.md`.

| Item | Origin | Status in code |
|---|---|---|
