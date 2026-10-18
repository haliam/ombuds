# Backlog — open items from the W1–W3 reviews

The three stage reviews (`w1_review_pre_w2_plan.md`, `w2_review_pre_w3_plan.md`, `w3_review_pre_w4_plan.md`) were deleted once every required task (T-*, P-*) was done. They stay in git history. These optional findings were still open in the code on 2026-10-18.

| Item | Origin | Status in code |
|---|---|---|
| Auth on `/approvals/*`, with `approver` derived from the token | W3 F-03, W2 F-13 | No token check; `approver` is self-declared, so audit rows record an unverified actor |
| Agent-level eval dataset (claim text → expected eligibility/escalation) | W3 F-07, W1 F-11 | `evals/datasets/airline_claims.jsonl` is empty; only retrieval is evaluated |
| CI (lint + unit; integration with a pgvector service) | W3 F-10, W2 O-4 | No `.github/workflows` |
| Configurable `ANTHROPIC_MAX_TOKENS` (suggested default 4096) | W2 O-5, W1 F-09 | Hardcoded 1024 in `providers/anthropic.py`; truncation means escalation |
| Bind the compose API port to localhost | W2 O-6 | `docker-compose.yml` publishes `8000:8000` |
| Delete dead stubs (`db_models.py`, `application/policies.py`) | W3 F-11 | Still one-line stubs; `tests/e2e/*` are placeholders for the compose smoke test |
| Pin the `uv` image tag in the Dockerfile | W3 F-11 | `ghcr.io/astral-sh/uv:latest` |
| Fix `scripts/compare_providers.py` run line | W3 F-11 | Says `--group scripts`; no such group in `pyproject.toml` |
| Frozen settings object instead of import-time env reads | W3 F-09 | Still module-level in `config.py`; W4 added more settings |

Not re-verified: small W1/W2 hygiene items (`McpToolClient` enter leak, `FallbackProvider` docstring).
