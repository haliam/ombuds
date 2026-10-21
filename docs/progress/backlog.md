# Backlog — open items from the W1–W3 reviews

The three stage reviews (`w1_review_pre_w2_plan.md`, `w2_review_pre_w3_plan.md`, `w3_review_pre_w4_plan.md`) were deleted once every required task (T-*, P-*) was done. They stay in git history. These optional findings were still open in the code on 2026-10-18.

| Item | Origin | Status in code |
|---|---|---|
| Auth on `/approvals/*`, with `approver` derived from the token | W3 F-03, W2 F-13 | No token check; `approver` is self-declared, so audit rows record an unverified actor |
| Agent-level eval dataset (claim text → expected eligibility/escalation) | W3 F-07, W1 F-11 | `evals/datasets/airline_claims.jsonl` is empty; only retrieval is evaluated |
| CI (lint + unit; integration with a pgvector service) | W3 F-10, W2 O-4 | No `.github/workflows` |
| Raise the `ANTHROPIC_MAX_TOKENS` default to 4096 | W2 O-5, W1 F-09 | Configurable since ADR-0018; the default is still 1024, and truncation means escalation |
| Bind the compose API port to localhost | W2 O-6 | `docker-compose.yml` publishes `8000:8000` |
| Delete dead stubs (`db_models.py`, `application/policies.py`) | W3 F-11 | Still one-line stubs; `tests/e2e/*` are placeholders for the compose smoke test |
| Pin the `uv` image tag in the Dockerfile | W3 F-11 | `ghcr.io/astral-sh/uv:latest` |
| Fix `scripts/compare_providers.py` run line | W3 F-11 | Says `--group scripts`; no such group in `pyproject.toml` |
| Frozen settings object instead of import-time env reads | W3 F-09 | Still module-level in `config.py`; W4 added more settings |

Not re-verified: small W1/W2 hygiene items (`McpToolClient` enter leak, `FallbackProvider` docstring).

## Added from `/codebase-review W4 W5` (2026-10-18)

Full detail in [`w4_review_pre_w5_plan.md`](w4_review_pre_w5_plan.md). The four required pre-W5 tasks (P-1 to P-4: approval recovery route, loopback ports and OPA exposure, `/approvals` auth, docs reconciliation) are tracked there, not here. The optional items are:

| Item | Origin | Status in code |
|---|---|---|
| Agent-level eval dataset and runner | W4 O-1 (W3 F-07) | Same gap as above; tracing now exists to record runs. The strongest W5 candidate |
| Explicit `env` for the MCP subprocess (`DATABASE_URL`, `OPA_*`, `PAYOUT_LIMIT_EUR`, `OTEL_*`) | W4 F-05 | `McpToolClient` passes none; the child gets only `HOME`/`PATH`-style defaults, so `use_mcp=True` in Docker would hit `localhost` defaults |
| Audit the out-of-scope tool call and the injection escalation; span the approvals routes; fix the "must not proceed unaudited" docstring | W4 F-06 | Scoped-out calls and injection hits leave no audit row; approval rows have a null `trace_id`. Needs migration 0004 |
| Pin `@scalar/api-reference` and add an OPA healthcheck | W4 F-08 | `/scalar` loads an unpinned CDN script; `api` waits for OPA only with `service_started` |

## Added from `/codebase-review W4 W5` second pass (2026-10-21)

Full detail in [`w4_review_pre_w5_plan_rev2.md`](w4_review_pre_w5_plan_rev2.md). Design notes for the W5 tasks are in `tasks.md`.

| Item | Origin | Status in code |
|---|---|---|
| `make lint` fails on two E501 lines | rev2 F-01 | `api/routes.py:76`, `audit_repository.py:25` |
| Tests for ADR-0018: no failover on `BudgetExceededError`, one shared `process_budget()` | rev2 F-06 | Neither claim has a test |
