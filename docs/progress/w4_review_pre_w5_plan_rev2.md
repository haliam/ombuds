# W4 Review & Pre-W5 Plan (second pass)

_Reviewed 2026-10-21 on branch `main` @ `3e1746f`. `make lint`: **fails**, 2 × E501 (ruff format and mypy strict are clean on 182 files). `tests/unit`: 355 passed. Integration/e2e: read only (they need Docker and keys). No `.codegraph/` index exists, so I used grep and direct reads._

**Stage inference and file name.** No arguments were given. `tasks.md` has Weeks 1–4 fully checked and Week 5 untouched, so this is W4 done, W5 next. The first review exists only in git history (2026-10-18, `360b5c5`), so I wrote this one beside it instead of overwriting it. It is a refresh: the earlier review's four required tasks became the W5 plan in `tasks.md`, and none has landed yet. The only code change since that review is ADR-0018 (the LLM spend cap, plus a configurable `ANTHROPIC_MAX_TOKENS`). Everything else since is docs and diagrams.

---

## 1. Current Project State

**Architecture.** The feature-sliced layout (ADR-0002) holds. I grepped the import graph again:
- Nothing in `domain/` imports `platform/` or `features/`.
- The only `platform/ → features/` import is `platform/mcp/server.py`, a documented composition root.
- There is no `except Exception` and no bare `except` anywhere in `src/`.
- The approval store is composed in one place, `application/runtime.py`: `PolicyChecked(Executing(Audited(Postgres)))`. The tool registry is `Traced(Audited(registry))`.

**What runs today.**
- Triage over a LangGraph tool loop, with sync and SSE endpoints.
- RAG over pgvector.
- Postgres-backed approvals with exactly-once execution.
- An MCP server over stdio.
- PII redaction, injection detection, an OPA payout policy, an append-only audit log and OpenTelemetry spans.
- New since the last review: a process-wide LLM spend cap (`UsageBudget` and `BudgetedProvider`, ADR-0018). A refused turn becomes a 429, or an `error` frame on the SSE stream.

**Still scaffold.** `db_models.py` and `application/policies.py` (one-line stubs), `tests/e2e/*`, and `evals/datasets/airline_claims.jsonl` (empty).

**Still open from the last review's findings.** These are exactly the W5 and W6 plan in `tasks.md`:
- the unreachable approval-recovery path;
- the ports published on all interfaces, and the unauthenticated OPA;
- the unauthenticated `/approvals` and triage routes;
- the stale README.

**Overall.** The code is consistent, typed and well tested, and ADR-0018 followed the decorator pattern again, with no node or tool edits. The one new problem is that `make lint` is red on `main`, because nothing runs it automatically. W5 is a good plan, but it makes four changes to the same few files (`docker-compose.yml`, `guardrails/api.py`, `config.py`, `api_app.py`), so order and a few design details matter (F-03, F-04).

---

## 2. W4 Assessment

W4's four tasks were assessed in the 2026-10-18 review and the code has not changed under them. I re-ran the checks and re-read the touched code. The table lists what is new.

| Stage task | Implemented in | Verdict |
|---|---|---|
| OPA/Rego payout policy | `policy_engine.py`, `policy_checked_store.py`, `policies/*.rego` | ✅ Unchanged. Port exposure is still open (W5 task 1). |
| Audit trail | `audit_log.py`, `audited_*.py`, `audit_repository.py`, migration 0003 | ✅ Unchanged. Coverage gaps are scheduled in W6. |
| OpenTelemetry tracing | `tracing.py`, `traced_*.py` | ✅ Unchanged. `tasks.md` was ticked in #54. |
| Architecture diagram + README | `README.md`, `docs/architecture.md`, `docs/diagrams/*` | ⚠️ `architecture.md` and the diagrams were reconciled (#57). **README is still stale** (F-05). |
| **ADR-0018 spend cap (not a board task)** | `ai/budget.py`, `providers/budgeted.py`, `providers/fallback.py` (`process_budget`), `ai/usage.py`, `api_app.py` | ✅ Sound design and well tested. A few fail-open edges are noted in F-06. It also introduced a lint error (F-01). |

**Carry-over from the previous review.**

| Previous item | Status |
|---|---|
| P-1 Recoverable approved-but-failed requests | Open. W5 task 2. |
| P-2 Loopback ports, OPA healthcheck | Done (W5 network exposure). |
| P-3 Auth on `/approvals` | Open. W5 task 3, now widened to the triage routes. |
| P-4 Docs reconciliation | Partly done: `tasks.md`, task summaries, `architecture.md` and diagrams. **README still open** (W5 task 5). |
| O-1 Agent-level eval | Open. W6. |
| O-2 MCP subprocess `env` | Open. W6. |
| O-3 Configurable `MAX_TOKENS` | **Done** (ADR-0018). The default is still 1024, and the backlog line is stale. |
| O-4 Audit gaps and approval spans | Open. W6. |
| O-5 CI | Open. W6 task 1. F-01 shows why it matters. |
| O-6 Hygiene batch | Open. W6. |
| O-7 Frozen settings | Open. It now matters for W5 auth (F-03). |

**Claims vs code (new or re-checked).**

| Invariant asserted | Enforced by | Pinned by |
|---|---|---|
| ADR-0018: a spent budget refuses the turn before any model call | `UsageBudget.check()` is called at the top of `BudgetedProvider.run_turn` and `stream_turn` | `test_run_turn_refuses_without_calling_the_model…`, `test_budget.py` ✅ |
| ADR-0018: failover is charged at the fallback model's price | Each adapter gets its own `BudgetedProvider(adapter, model, …)` | `test_fallback_provider_wiring.py` (updated) ✅ |
| ADR-0018: `BudgetExceededError` never fails over to a cheaper model | `FallbackProvider` catches only `ProviderUnavailableError` | **No test** (F-06) ⚠️ |
| ADR-0018: HTTP 429 and an SSE `error` frame | `_budget_exceeded` handler, `_to_sse` | `test_api_app.py` ✅ |
| One ledger per process | `@lru_cache process_budget()` | **No test** (F-06) ⚠️ |
| Approved request executes exactly once | Unchanged | ✅ |
| "Failed executor is recoverable" | `execute_approved` exists | Unit test on the store only. No route (W5 task 2). ❌ |
| README: "Tracing and audit are not built" | n/a | False since W4 ❌ (F-05) |

---

## 3. Findings

### F-01 — `make lint` is red on `main`, and nothing would notice
- **Area:** Developer experience / CI
- **Current situation:**
  - `ruff check` reports two E501 (line > 120):
    - `features/claims_triage/api/routes.py:76`, the 128-character docstring line added with ADR-0018;
    - `platform/infrastructure/audit_repository.py:25`, a 140-character docstring line.
  - `make test` is `make lint` then pytest, so it fails before running a single test.
  - The previous review recorded lint as clean. I cannot tell whether the `audit_repository.py` line changed since, since `git blame` points at #43.
  - `pre-commit` is opt-in and there is no `.github/workflows`.
- **Problem / risk:** Every W5 commit is supposed to pass `make test`, and the first one will fail on lines it did not touch. It also shows that the checks only run when someone remembers to.
- **Recommended change:**
  - Wrap the two lines. For the `audit_repository.py` docstring, W6 will rewrite it anyway ("must not proceed unaudited"), so wrap it now and let W6 correct the wording.
  - Do not bring the CI task forward, but do run `uv run pre-commit install` if not done.
- **Reason:** Two-minute fix that restores a trustworthy baseline.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W5:** Yes

### F-02 — Approved-but-failed requests are still stuck (W5 task 2): the shape of the fix
- **Area:** Correctness / governance
- **Current situation:**
  - Unchanged from the last review's F-01. `execute_approved` exists only on `ExecutingApprovalStore`, with no caller outside `approve`.
  - The `ApprovalStore` protocol does not include it.
  - Both decorators above and below it in the stack (`PolicyCheckedApprovalStore` outside, `AuditedApprovalStore` inside) have no pass-through.
  - `app.state.approvals` is the *outermost* store, so the route cannot reach `execute_approved` today.
  - `approve` in `guardrails/api.py` catches only `ApprovalNotFoundError` and `ApprovalStateError`.
  - Nothing outside `executors.py` raises `ToolExecutionError` in the execution path, and nothing documents which exception types an executor may raise.
- **Problem / risk:**
  - W5 task 2 is the right fix. Three details decide whether it stays small:
    1. If `execute_approved` goes on the shared `ApprovalStore` protocol, the in-memory `ApprovalGate` (the test fake) must also implement it, which makes no sense for a store with no executors.
    2. Catching only `ToolExecutionError` is correct, but a Postgres error from the executor would still be a 500 while the request is `APPROVED`.
    3. The request state after a failed approve must be reported (`APPROVED`, retry via `/execute`), not just a generic message.
- **Recommended change:**
  - Add a second small protocol in `approval_gate.py` (for example `ExecutableApprovalStore(ApprovalStore)` with `execute_approved`). `ExecutingApprovalStore` and the two decorators implement it by delegation. `create_app` and `build_runtime` type `approvals` as that protocol, and the route depends on it. `ApprovalGate` stays unchanged.
  - Translate `ToolExecutionError` to a 502-style JSON body that includes the request id and `status: approved`. Let unexpected exceptions propagate (a 500 is honest for a bug), but log them with the request id.
  - Make the retry route return 409 for any non-`APPROVED` request. The existing `ApprovalStateError` already does that.
  - Test through the real decorator stack with a failing executor, not a mock store. The unit test in `test_executing_store.py` is the template.
- **Reason:** Keeps the protocol honest and makes the guarantee real.
- **Priority:** High
- **Estimated complexity:** Small–Medium
- **Must fix before W5:** No (it is a W5 task)

### F-03 — W5 auth: three design points that the plan does not yet settle
- **Area:** Security / design
- **Current situation:**
  - `OPA_URL`, `DATABASE_URL` and every other setting are read at import time in `config.py`.
  - `create_app()` is called at import (`app = create_app()`), and tests build apps with `create_app(approvals=…)` and `TestClient`.
  - Compose healthchecks `api` with `GET /openapi.json`.
  - `/scalar`, `/docs` and `/redoc` are public by default.
  - The approvals body requires `approver: str` (`min_length=1`).
  - The task says: bearer tokens that fail closed, separate credentials for triage vs approve/deny, `approver` taken from config.
- **Problem / risk:**
  1. **Settings at import time make fail-closed auth hard to test.** A dependency that reads a module constant needs `monkeypatch.setattr(config, …)` in every test. Forgetting it makes tests pass with the token unset, which is exactly the failure the design says must be impossible.
  2. **The healthcheck breaks** if the auth dependency is applied app-wide. Compose would never see `api` healthy, and `make up` would hang.
  3. **Docs pages:** `/openapi.json` and `/scalar` publish the whole API surface. That is fine locally, but state the choice.
  4. **`approver` from config**: a single configured identity means every audit row says the same name. That is honest ("whoever holds the approver token"), but the ADR should say so, and the body field should be removed or ignored, not kept as a second source of truth.
- **Recommended change:**
  - Put the two token checks in one small module (for example `platform/guardrails/auth.py`): `require_triage_token` and `require_approver_token`. Each is a FastAPI dependency that calls a small `get_auth_settings()` function, which tests override with `app.dependency_overrides`. Use `secrets.compare_digest`. If the configured token is empty, reject every request.
  - Attach `require_approver_token` to the approvals router and `require_triage_token` to the triage router. Do not attach either to the app, so `/openapi.json` stays open for the healthcheck. Say in the ADR that docs are public by design.
  - Remove `approver` from `ApprovalDecisionRequest`. Pass the configured identity to the store.
  - `GET /approvals` and `GET /approvals/{id}` are reads, but they expose payloads. Put them behind the approver token too.
  - Do the audit-trail tests with the override, so the unauthenticated path is covered too.
- **Reason:** These are the places where a "fail closed" claim would otherwise be unenforced or untestable.
- **Priority:** High
- **Estimated complexity:** Small–Medium
- **Must fix before W5:** No (it is a W5 task)

### F-04 — W5 task order and the weak DB default touch the same files
- **Area:** Planning / configuration
- **Current situation:**
  - `config.py` falls back to `postgresql://ombuds:ombuds@localhost:5433/ombuds`.
  - `docker-compose.yml` hard-codes the same password in three places: `db`, `migrate-ingest` and `api`. `.env.example` repeats it.
  - `tests/integration/conftest.py` and the Makefile (`db-up`, `test-integration`, `ingest`) rely on that default.
- **Problem / risk:**
  - Removing the default without a plan breaks `make test-integration`, `make ingest` and `make eval` for anyone without a `.env`.
  - The compose file also needs a single source for the password.
  - Both are manageable, but they are easy to get half right.
- **Recommended change:**
  - Compose: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set it in .env}` and a `DATABASE_URL` built from it, so there is one source. The `:?` form makes compose fail with a clear message.
  - `config.py`: raise a clear `RuntimeError` at the point of use when `DATABASE_URL` is unset, unless `OMBUDS_ALLOW_DEV_DEFAULTS=1`. Do not raise at import, or every unit test that imports `config` fails.
  - Keep `.env.example` as the one place with a placeholder value, and make `make db-up` and the integration conftest read `.env`.
  - Do this task *after* the ports task, since both edit `docker-compose.yml`.
- **Reason:** Order and one source of truth for the password avoid a half-broken dev loop.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W5:** No

### F-05 — README still says tracing and audit are not built
- **Area:** Documentation
- **Current situation:**
  - README line 81, "Known limitations: **Tracing and audit are not built.**"
  - README line 105, "Status: Weeks 1–3 built, pre-W4 refactor done … observability and the audit trail are not."
  - README line 36 also says `log_claim` is the only guarded tool the agent can call. That matches the code (`AGENT_TOOL_NAMES`) but not the limitation text.
  - `architecture.md`, `tasks.md` and the diagrams are already correct.
- **Problem / risk:** The README is the first thing a reviewer opens, and it contradicts the repo. Nothing else in the docs is stale, so this is the last item.
- **Recommended change:** Leave it to W5 task 5, which should run last so it describes the final auth and port behaviour. Update the limitations list, the status line and the week table together. Also tick the AGENTS.md "Status" date.
- **Reason:** Already scheduled correctly.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W5:** No

### F-06 — The spend cap (ADR-0018) fails open in a few small ways
- **Area:** AI cost control / testability
- **Current situation:**
  - `ProviderTurn.usage` and `TurnDone.usage` default to `TokenUsage()` (zero). A provider that forgets to report usage is charged nothing.
  - `BudgetedProvider.stream_turn` charges only when it sees `TurnDone`. If the client disconnects mid-stream, the generator is closed early and that turn is never charged.
  - Prices are keyed by exact model name (`LLM_PRICES_USD_PER_MTOK`). Changing `ANTHROPIC_MODEL` without updating the table charges every turn at the unknown price (15/75), which is safe but surprising.
  - "`BudgetExceededError` never fails over" and "one ledger per process" (`process_budget`) have no test.
  - `process_budget()` lives in `providers/fallback.py`, next to the factory that uses it, with a lazy `from ombuds import config`.
  - The 429 body includes the spend figures. That is harmless once `/triage` is authenticated.
- **Problem / risk:**
  - None of these is a defect today: `AnthropicProvider` is the only wired provider and it reports usage.
  - The disconnect case undercounts by at most one turn, and the ADR already says the cap is an estimate and the provider limit is the backstop.
  - The two untested claims are the ones the ADR leans on.
- **Recommended change:**
  - Add two unit tests: `FallbackProvider` lets `BudgetExceededError` propagate without calling the fallback, and `process_budget()` returns the same object twice. Both are a few lines.
  - Charge in a `finally` in `stream_turn` only if it can be done without double-charging. Otherwise leave it and keep the ADR's note.
  - Leave the default `usage`, the file placement and the price-table design alone.
- **Reason:** Pins the two claims the ADR makes. The rest is fine at this size.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W5:** No

---

## 4. Required Refactoring Before W5

### P-1 — Make `make lint` green
- **Description:** Wrap the two over-long docstring lines (F-01).
- **Files/modules likely affected:** `src/ombuds/features/claims_triage/api/routes.py`, `src/ombuds/platform/infrastructure/audit_repository.py`.
- **Reason:** `make test` fails before running any test, so every W5 commit would start red.
- **Acceptance criteria:**
  - `make lint` exits 0.
  - `uv run pytest tests/unit` still passes (355).
  - Docstring wording is unchanged apart from line breaks.
- **Dependencies:** None.

---

## 5. Optional Improvements

| ID | Improvement | When |
|---|---|---|
| O-1 | Use the shape described in F-02 for the recovery route (second protocol, `ToolExecutionError` → JSON body with `status: approved`) | Inside W5 task 2 |
| O-2 | Use the shape in F-03 for auth (one `auth.py`, overridable settings function, routers not app, `/openapi.json` open) | Inside W5 task 3 |
| O-3 | Compose password from one `POSTGRES_PASSWORD`, `config.py` raises at use unless a dev flag is set (F-04). Run after the ports task | Inside W5 task 4 |
| O-4 | Two tests pinning ADR-0018 (no failover on budget, one shared ledger) (F-06) | Any time; ~15 minutes |
| O-5 | Remove the stale "O-3 `ANTHROPIC_MAX_TOKENS`" line in `backlog.md` | With the W5 docs task |
| O-6 | Execute W5 in this order: ports → recovery route → auth → DB default → README | Planning only |

---

## 6. Proposed Pre-W5 Execution Plan

- [ ] P-1 — Fix the two E501 lines so `make lint` is green

Then start W5 from `tasks.md` in the order in O-6. One commit per task, per the project's habit.

---

## 7. Final Recommendation

**Ready for W5 after the required refactoring.**

The code is in the same good shape as the last review found it, and the one change since (the spend cap) was added the way the rest of the system is built: a decorator at a seam, with the invariants unit-tested. Every governance invariant I traced still has code that enforces it and a test that pins it, except the recovery path, which W5 task 2 closes. The only blocker is small and mechanical: `make lint` is red on `main` (P-1). The W5 plan is the right plan. F-02 to F-04 only tighten how the tasks are built, so the "fail closed" claims are testable and the compose and config edits do not collide.

**Considered and left alone:**
- **Policy not re-evaluated at approve; audit insert not in the same transaction; sync handlers and `urllib` for OPA.** These are documented in ADR-0015 and ADR-0016 and unchanged.
- **`process_budget()` in `fallback.py`, and the default zero `TokenUsage`.** The placement is slightly odd but has a single caller. The default is only a risk with a second provider.
- **Embeddings are not metered.** ADR-0018 says so, and the cost is cents.
- **Per-worker ledger and the concurrent overshoot.** Documented in the ADR. The provider limit is the backstop (also a W6 manual check).
- **Hand-maintained `policy_version`, regex PII and injection detectors, the `tools/__init__.py` adapter boilerplate, and the provider fallback design.** Unchanged since the last review.
- **A frozen settings object for the whole app.** F-03 asks only for an overridable function for auth settings. A full settings refactor is not needed for W5.
