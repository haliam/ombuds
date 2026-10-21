# W4 Review & Pre-W5 Plan

_Reviewed 2026-10-18 on branch `pre_w5_review` (`main` @ `360b5c5`). `make lint`: clean (ruff, ruff format, mypy strict on 177 files). `tests/unit`: 347 passed. Integration/e2e: read only (they need Docker and keys). No `.codegraph/` index exists, so I used grep and direct reads._

**Stage inference.** `docs/progress/tasks.md` has no W5 section. The README roadmap stops at Week 4 ("Observability, OPA/Rego policy, audit trail, architecture docs"). I read "next" as the polish, demo and interview phase after the build weeks. Nothing here assumes a particular W5 scope.

---

## 1. Current Project State

**Architecture.** The feature-sliced layout (ADR-0002) holds. I grepped the import graph. Nothing in `domain/` imports `platform/` or `features/`. The only `platform/ → features/` import is `platform/mcp/server.py`, which is a documented composition root (ADR-0003). `api_app.py` and the MCP server both build one `ClaimsTriageRuntime` through `application/runtime.py`, so the API and the MCP subprocess are wired identically.

**What runs today.**
- Triage runs through a LangGraph tool loop. The sync and SSE endpoints share one preamble, so they cannot drift.
- RAG over pgvector, behind a relevance floor.
- Postgres-backed approvals. Approving a request runs its executor exactly once and writes `claims` or `payments` rows.
- The MCP server over stdio.
- PII redaction and injection detection.
- **W4 additions.** The stack from the outermost layer in is: `PolicyCheckedApprovalStore` → `ExecutingApprovalStore` → `AuditedApprovalStore` → `PostgresApprovalStore`. A payout above `PAYOUT_LIMIT_EUR` is denied at submit by an OPA sidecar (fail-closed). Tool calls go through `TracedDispatcher` → `AuditedDispatcher` → the registry. Providers are wrapped by `TracedProvider`. An append-only `audit_log` table is enforced by DB triggers (migration 0003). Spans cover LLM turns, tool calls, policy checks and the triage run, and each audit row carries the active `trace_id`.

**Still scaffold.** `db_models.py`, `application/policies.py`, `tests/e2e/*` and the agent-level eval dataset (`airline_claims.jsonl`, 0 lines).

**Overall.** The code is consistent, typed and well tested. W4 was added as decorators at the seams the W3 review pointed to (F-05), with no node edits, so the structure needed no redesign. The real problems are in operations and exposure, in one recovery path that cannot be reached, and in docs that no longer match the code.

---

## 2. W4 Assessment

| Stage task | Implemented in | Verdict |
|---|---|---|
| OPA/Rego payout policy | `guardrails/policy_engine.py`, `policy_checked_store.py`, `policies/payout_approval.rego` (+ `_test.rego`), ADR-0015 | ✅ Fails closed (unit and integration tests). The limit is passed in as input, not hardcoded (W3 F-08 done). Missing and invalid fields are covered by reason codes. ⚠️ The container's port is published unauthenticated (F-02). Not re-evaluated at approve, which ADR-0015 already documents. |
| Audit trail | `guardrails/audit_log.py`, `audited_dispatcher.py`, `audited_store.py`, `infrastructure/audit_repository.py`, migration 0003, ADR-0016 | ✅ Append-only is a database guarantee, pinned by `test_audit_rows_cannot_be_updated_deleted_or_truncated`. PII-safe by construction. ⚠️ Coverage gaps and an overstated docstring (F-06). The actor field is still unauthenticated (F-03). |
| OpenTelemetry tracing | `observability/tracing.py`, `traced_dispatcher.py`, `ai/providers/traced.py`, `triage_use_case.py`, ADR-0017 | ✅ No-op by default. Attributes are IDs and counts only, with the exception type but not its message. The streaming span handles the threadpool case correctly. ❌ `tasks.md` still shows this task unchecked (F-04). |
| Architecture diagram + README | `README.md`, `docs/architecture.md`, `docs/diagrams/*` | ⚠️ Delivered, but written before the other three tasks landed and not updated since (F-04). |

**Carry-over from the W3 review (P-1 to P-4 and optional items).**

| W3 item | Status |
|---|---|
| P-1 to P-4 (composition-root wiring, executors, shared preamble, docs) | Done. `_GATE` is gone, and the preamble is one helper (`_prepare_run`). |
| F-03 Auth on `/approvals` | **Open.** It was to be done inside the audit task and was not (F-03 below). |
| F-05 Dispatcher decorators | Done, as recommended. |
| F-07 Agent-level eval | **Open.** Its precondition (tracing to record runs) now exists (O-1). |
| F-08 Threshold as OPA input | Done. |
| F-09 Frozen settings | Open, optional. W4 added six more import-time settings. |
| F-10 CI | Open. |
| F-11 Hygiene (dead stubs, uv tag, script docstring) | Open. |
| W2 O-5 `MAX_TOKENS`, W2 O-6 localhost bind | Open (O-3; F-02 absorbs the port part). |

All open items are also in `docs/progress/backlog.md`.

**Claims vs code.**

| Invariant asserted | Enforced by | Pinned by |
|---|---|---|
| Approved executes exactly once | `PENDING→APPROVED` and `APPROVED→EXECUTED` compare-and-set in `PostgresApprovalStore`, executor idempotent | `test_concurrent_approvals_execute_exactly_once`, `test_a_second_approval_raises…` ✅ |
| Policy fails closed | `OpaHttpPolicyEngine.evaluate` catches transport and shape errors, plus Rego defaults to deny | `test_policy_engine.py` unit and integration ✅ |
| Denied payout never reaches the human queue | `PolicyCheckedApprovalStore.submit` raises before `inner.submit` | `test_policy_checked_store.py` ✅ |
| Audit is append-only | Triggers in migration 0003 | Integration test ✅ |
| Spans and audit never hold raw PII | Attributes are IDs and counts; the dispatcher redacts the audit arguments | `test_tracing.py` and the audited-dispatcher tests ✅ |
| "A failed executor is recoverable" (ADR-0009 addendum, `executing_store.py`) | `execute_approved` exists | A unit test on the store only. **No production caller (F-01).** ❌ |
| "An action must not proceed unaudited" (`audit_repository.py` docstring) | `record` raises on a DB error | The audit row is written after the effect. ⚠️ Overstated (F-06). |
| README: "Tracing and audit are not built" | n/a | False since W4 (F-04). ❌ |

---

## 3. Findings

### F-01 — An approved request whose executor fails is stuck `APPROVED` forever, and the "recovery path" has no caller
- **Area:** Correctness / governance (approval lifecycle)
- **Current situation:**
  - `ExecutingApprovalStore.approve` moves the request to `APPROVED`, then runs the executor, then wins `APPROVED→EXECUTED`.
  - The docs promise that if the executor fails (a DB hiccup, or `ensure_claim_logged_for` raising `ToolExecutionError` because the claim was never logged), the request stays `APPROVED` and `execute_approved` re-runs it safely.
  - `grep execute_approved src` finds only its definition and the call inside `approve`. It is not on the `ApprovalStore` protocol, and `PolicyCheckedApprovalStore`, the outermost store, does not expose it.
  - `POST /approvals/{id}/approve` catches only `ApprovalNotFoundError` and `ApprovalStateError`. An executor failure is therefore an unhandled 500.
  - A second approve then returns 409, because the request is no longer `PENDING`.
- **Problem / risk:**
  - A human approval has been recorded, no effect happened, and no route can finish the job. The request is not listed as pending either (`list_pending` filters on `PENDING`).
  - The caller sees a 500 with no machine-readable reason. The most likely trigger is the most natural demo mistake, approving `issue_payment` for a claim whose `log_claim` was never approved.
  - It undermines the project's headline claim, "approved → executed exactly once, recoverably".
- **Recommended change:**
  - Map executor failures in the `approve` route to a clear 4xx/5xx JSON error that says the request is still `APPROVED` and can be retried. Catch `ToolExecutionError` specifically, not `Exception`.
  - Add one retry route, `POST /approvals/{id}/execute`, that calls `execute_approved`. This means adding it to the `ApprovalStore` protocol, or to a small second protocol that `ApprovalGate` and the decorators implement.
  - Add an API-level test for each of the two paths.
- **Reason:** It makes a documented behaviour true, with a small change on the existing seam.
- **Priority:** High
- **Estimated complexity:** Small–Medium
- **Must fix before W5:** Yes

### F-02 — Compose publishes OPA, Postgres and the API on every interface; unauthenticated OPA lets anyone rewrite the payout policy
- **Area:** Security / deployment
- **Current situation:**
  - `docker-compose.yml` publishes `8181:8181` (OPA), `5433:5432` (Postgres, password `ombuds`) and `8000:8000` (API) with no host binding.
  - OPA runs `opa run --server --addr=0.0.0.0:8181` with no `--authentication` or `--authorization` flags. By default its REST API accepts policy writes (`PUT /v1/policies/…`) and data writes from anyone who can reach the port.
  - Only the `api` container needs OPA and `db`; both are on the compose network.
- **Problem / risk:**
  - The payout policy is the project's "non-negotiable" guardrail (AGENTS.md), and anyone on the same network could replace it with `allow := true` or overwrite what it reads. The fail-closed design guards against OPA being down, not against OPA being reconfigured.
  - Exposed Postgres with default credentials also allows `audit_log` writes of arbitrary rows, although its triggers do block UPDATE, DELETE and TRUNCATE.
  - This matters most if W5 includes a shared demo, a cloud VM or a laptop on conference Wi-Fi.
- **Recommended change:**
  - Bind published ports to loopback (`127.0.0.1:…`) for `db`, `opa` and `api`, or drop the `opa` publish entirely and keep a loopback-only mapping for dev.
  - If the port must stay reachable beyond the host, OPA's own protection is an authorization policy (`--authentication=token --authorization=basic`). I have not verified that setup here, so treat it as a follow-up, not part of this task, and record the limitation in ADR-0015.
  - Do not add a gateway or secrets manager for this.
- **Reason:** One config edit removes the realistic attack path. The remaining work is documentation.
- **Priority:** High
- **Estimated complexity:** Small
- **Must fix before W5:** Yes

### F-03 — `/approvals` is unauthenticated, so the audit trail's "who approved" is unverified
- **Area:** Security / governance
- **Current situation:**
  - `approve` and `deny` accept any caller and a free-text `approver`. `AuditedApprovalStore` now writes that string to `audit_log.detail.approver`.
  - W3 F-03 said to add a bearer-token dependency "inside the W4 audit-trail task, where the actor field is first consumed". That was not done. The README lists it as a known limitation.
- **Problem / risk:**
  - The audit trail is the evidence of who approved a payout, and anyone who can reach port 8000 can approve, deny or list pending requests under any name.
  - Together with F-02 this is the one place where "human in the loop" is weaker than the rest of the design.
- **Recommended change:**
  - One FastAPI dependency on the `/approvals` router that checks `Authorization: Bearer <APPROVALS_API_TOKEN>` from the environment, using `secrets.compare_digest`. Fail closed when the variable is unset.
  - Take `approver` from a second setting (or an identity tied to the token) instead of the request body. Keep the body field optional only as a note.
  - Do not build a user system.
- **Reason:** It makes the actor field in `audit_log` trustworthy for the cost of a single dependency.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W5:** Yes

### F-04 — Docs and the task board disagree with the code about W4
- **Area:** Documentation
- **Current situation:**
  - README "Known limitations": "Tracing and audit are not built … policy decisions are not yet persisted". README status line: "observability and the audit trail are not [built]". The status heading still says "Weeks 1–3 built".
  - `docs/architecture.md` ("Not built yet"): "OpenTelemetry tracing is Week 4 work and exists as a stub … The diagram does not draw any of the three yet."
  - `docs/progress/tasks.md`: `- [ ] Add OpenTelemetry tracing`, although it shipped in PR #43 with ADR-0017.
  - The `architecture` and `guardrails-pipeline` diagrams do not show the policy, audit or tracing decorators.
- **Problem / risk:** The README is the interview artefact. Underclaiming is harmless but misleading, and AGENTS.md says a stale line is worse than none. It also means the status table you would point a reviewer at is wrong.
- **Recommended change:**
  - Update the README (limitations, status, week table) and `architecture.md` "Not built yet".
  - Tick the OTel task in `tasks.md` with its ADR link and add its `task_summaries.md` entry (check that the other W4 tasks have one).
  - Bump the affected diagram pages (`architecture`, `guardrails-pipeline`, `approval-lifecycle` if it shows the store stack), following `docs/code-style.md`'s diagram rules.
- **Reason:** Cheap, and these are the first documents anyone reads.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W5:** Yes

### F-05 — The MCP subprocess does not receive the app's configuration
- **Area:** Configuration / correctness (latent)
- **Current situation:**
  - `McpToolClient` builds `StdioServerParameters(command, args)` with no `env`. The MCP SDK then gives the child only its default whitelist (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `USER`; I printed it from the installed SDK).
  - `config.py` reads `DATABASE_URL`, `OPA_URL`, `PAYOUT_LIMIT_EUR` and `OTEL_*` from `os.environ`, with `load_dotenv()` as a fallback.
  - Locally the child finds the repo `.env` by walking up from `config.py`. In the Docker image, compose injects these variables into the *API* environment, and the child does not inherit them.
- **Problem / risk:**
  - `use_mcp=True` inside the compose stack would open `localhost:5433` (connection refused) and `localhost:8181`, which fails closed. Both are wrong for the container, and a changed `PAYOUT_LIMIT_EUR` would be silently ignored.
  - It is latent because no HTTP route sets `use_mcp`, and the integration test passes locally because of `.env`.
- **Recommended change:** Pass an explicit `env` to `StdioServerParameters` (the SDK default plus the specific `DATABASE_URL`, `OPA_*`, `PAYOUT_LIMIT_EUR`, `OTEL_*` and API keys it needs), assembled in the composition root or `triage_use_case`, not by copying the whole environment. Add a unit test on the parameters.
- **Reason:** Makes the "MCP path uses the same Postgres and policy as the API" statement (AGENTS.md, `runtime.py`) true in Docker as well.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W5:** No (Yes if W5 demos the agent over MCP in Docker)

### F-06 — Audit and trace coverage has gaps, and one docstring overstates it
- **Area:** Governance / observability
- **Current situation:**
  - `AuditedDispatcher` sits inside `scope_for_agent`, so a model's attempt to call a tool outside `AGENT_TOOL_NAMES` (for example `issue_payment`) returns an error result and is **never recorded**. That attempt is the most security-relevant event the audit could hold.
  - The pre-model injection escalation is not audited and has no span (ADR-0016 notes this, and it was W3 F-04's "injection hits are untraceable").
  - `/approvals` approve and deny open no span, so those audit rows have `trace_id = NULL`.
  - `PostgresAuditLog.record` says "an action must not proceed unaudited". In fact the row is written after the effect (ADR-0016 notes the non-atomicity), so a failing insert raises after the approval request exists.
- **Problem / risk:** "Log every tool call + decision" is the task's own definition, and the blocked attempts and the injection hits are decisions. The docstring promises an ordering the code does not give.
- **Recommended change:**
  - Add a small audit event for the two refusals (out-of-scope tool call, injection escalation), reusing `AuditLog` and a new `AuditKind` (the table's `CHECK` constraint needs migration 0004).
  - Wrap the approvals routes in a span.
  - Correct the docstring to say what is guaranteed.
  - Do not make the audit insert transactional with the state change unless W5 needs it. ADR-0016 deferred that deliberately.
- **Reason:** It completes the trail for the events that matter most, without changing the architecture.
- **Priority:** Medium
- **Estimated complexity:** Medium
- **Must fix before W5:** No

### F-07 — No agent-level eval, although the prompt policy requires one
- **Area:** Testing / AI practice (carry-over, W3 F-07 and W1 F-11)
- **Current situation:** AGENTS.md says a new prompt version "must run clean against `evals/datasets/`". `airline_claims.jsonl` is empty, and only retrieval is evaluated (`make eval`). The precondition W3 named, tracing to record runs, now exists.
- **Problem / risk:** A prompt or model change is unmeasured, and the eval seam is the one AI-engineering practice the repo cannot yet demonstrate end to end. The deterministic `verify_decision` still guards correctness, so it is not a safety issue.
- **Recommended change:** 15–25 claims (text, expected eligibility, expected escalation) run against a real model on demand, printing a report and never failing CI, like the retrieval eval. Log the trace id per case.
- **Reason:** It turns "prompt v5" into a measurement, and it is the most credible W5 artefact.
- **Priority:** Medium
- **Estimated complexity:** Medium
- **Must fix before W5:** No

### F-08 — Small hygiene items (carry-over plus two new)
- **Area:** Maintainability
- **Current situation:**
  - Carry-over: `db_models.py` and `application/policies.py` are one-line stubs; the Dockerfile uses `uv:latest`; `compare_providers.py` says `--group scripts`, which does not exist; `MAX_TOKENS` is hardcoded at 1024; there is no CI.
  - New: `/scalar` loads `https://cdn.jsdelivr.net/npm/@scalar/api-reference` with no pinned version. The OPA service has no healthcheck, and `api` waits only for `service_started`, so the first requests can fail closed for a few seconds.
- **Recommended change:** Batch these as in the backlog. Pin the Scalar version. Give OPA a healthcheck so `api` can wait on `service_healthy`. The official image is minimal, so verify what the healthcheck can run in it (I did not), or fall back to a retry in the API's startup.
- **Reason:** Low-cost cleanups.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W5:** No

---

## 4. Required Refactoring Before W5

### P-1 — Make approved-but-failed requests recoverable
- **Description:** Handle executor failures in the approve route and add a retry route over `execute_approved` (F-01).
- **Files/modules likely affected:** `platform/guardrails/approval_gate.py` (protocol, `ApprovalGate`), `executing_store.py`, `policy_checked_store.py`, `audited_store.py`, `platform/guardrails/api.py`, and their unit tests (`test_api`, `test_executing_store`) plus one integration test in `test_execution.py`.
- **Reason:** A documented guarantee has no reachable code path.
- **Acceptance criteria:**
  - Approving a payment for an unlogged claim returns a clear error body, not a 500, and the request stays `APPROVED`.
  - After the cause is fixed, `POST /approvals/{id}/execute` runs the executor once, the request becomes `EXECUTED`, and the audit trail shows it.
  - Calling it on a `PENDING`, `DENIED` or `EXECUTED` request gives 409 and writes nothing.
  - Exactly-once is unchanged (the concurrency test still passes).
- **Dependencies:** None.

### P-2 — Lock down the compose ports and OPA
- **Description:** Loopback-bind published ports so OPA's unauthenticated API is not reachable off-host (F-02), and make `api` wait for a healthy OPA if a working healthcheck can be found (from F-08).
- **Files/modules likely affected:** `docker-compose.yml`, ADR-0015 (a short "network exposure" note), `docs/guide/developer-guide.md` if a port changes.
- **Reason:** The payout policy can currently be rewritten by anyone who can reach the port.
- **Acceptance criteria:**
  - No service is reachable from outside the host by default.
  - `make up`, `make test-integration` and `make test-policy` still work.
  - A request to OPA's policy-write endpoint from a non-loopback address fails.
- **Dependencies:** None.

### P-3 — Authenticate `/approvals`
- **Description:** A bearer-token dependency on the approvals router, with the approver identity taken from configuration (F-03).
- **Files/modules likely affected:** `platform/guardrails/api.py`, `config.py`, `.env.example`, `docker-compose.yml` (env), tests, ADR-0016 or a short ADR-0018 note.
- **Reason:** The audit trail records an actor that anyone can forge.
- **Acceptance criteria:**
  - A request without the correct token gets 401, and an unset token setting rejects all requests.
  - The stored and audited `approver` comes from the configured identity, not the body.
  - Existing approval tests use `dependency_overrides` or pass the token.
- **Dependencies:** None (sensible after P-1, since both touch `api.py`).

### P-4 — Reconcile docs, task board and diagrams with W4
- **Description:** Update the README, `architecture.md`, `tasks.md`, `task_summaries.md` and the affected diagrams (F-04).
- **Files/modules likely affected:** `README.md`, `docs/architecture.md`, `docs/progress/tasks.md`, `docs/progress/task_summaries.md`, `docs/diagrams/{architecture,guardrails-pipeline,…}`, `docs/diagrams/README.md`, and AGENTS.md "Status" if its date needs bumping.
- **Reason:** Written last so it describes final behaviour (including P-1 to P-3).
- **Acceptance criteria:**
  - The README makes no "not built" claim for tracing, audit or policy persistence, and its known-limitations list matches the code (including whatever is left of the `/approvals` auth gap).
  - `tasks.md` shows W4 complete with ADR links.
  - The touched diagrams carry a bumped version and date.
  - Every command in AGENTS.md still runs.
- **Dependencies:** P-1, P-2, P-3.

---

## 5. Optional Improvements

| ID | Improvement | When |
|---|---|---|
| O-1 | Agent-level eval dataset and runner (F-07) | The strongest W5 candidate, now that tracing can record runs |
| O-2 | Pass explicit `env` to the MCP subprocess (F-05) | Before any demo of the agent over MCP in Docker; otherwise any time |
| O-3 | Configurable `ANTHROPIC_MAX_TOKENS` (default 4096), because truncation means escalation | Any time, ~15 minutes |
| O-4 | Audit the out-of-scope tool call and injection escalation, and span the approvals routes (F-06) | After P-1/P-3, as one small PR with migration 0004 |
| O-5 | One GitHub Actions workflow: `make lint` and unit tests, plus an integration job with pgvector and OPA services | Any time; tests mock the LLM, so no secrets are needed |
| O-6 | Hygiene batch: delete the two dead stubs, pin the uv image and Scalar versions, fix the script's run line (F-08) | Any time; ~30 minutes |
| O-7 | Frozen settings object built once in `create_app()` | Only if P-3 already touches config; W4 added six more import-time settings |

---

## 6. Proposed Pre-W5 Execution Plan

- [ ] P-1 — Recoverable approved-but-failed requests (retry route, clean error)
- [ ] P-2 — Loopback ports and OPA hardening, OPA healthcheck
- [ ] P-3 — Bearer-token auth on `/approvals`, configured approver identity
- [ ] P-4 — Docs, task board and diagram reconciliation

One commit per task, per the project's habit. Estimated effort: P-1 about two hours, P-2 an hour, P-3 an hour or two, P-4 an hour or two.

---

## 7. Final Recommendation

**Ready for W5 after the required refactoring.**

W4 was added the way the W3 review asked for, as decorators on the existing seams, and it is well done: lint and mypy are clean, 347 unit tests pass, the layering holds, and every governance invariant I traced (exactly-once execution, fail-closed policy, append-only audit, PII-free spans) has code that enforces it and a test that pins it. Nothing needs a redesign.

What stands in the way is four small things. One documented guarantee has no reachable code path, which is the "recoverable" half of the approval lifecycle (P-1). The payout policy server and the database are published unauthenticated (P-2), and the approval API that feeds the audit trail has no authentication (P-3). The README, the task board and the diagrams still describe the project as it was before W4 (P-4).

**Considered and left alone:**
- **Policy is not re-evaluated at approve.** ADR-0015 documents it. Lowering the limit does not cancel already-pending requests, and a human is still in the loop.
- **The audit insert is not in the same transaction as the state change.** ADR-0016 deliberately defers it, and threading a connection through the stores is not worth it yet.
- **Sync handlers and `urllib` for OPA.** FastAPI runs sync handlers in a threadpool, and the call is short, bounded by `OPA_TIMEOUT_SECONDS`, and fails closed.
- **Hand-maintained `policy_version := "1"`.** It is recorded in every audit row and is fine at one policy.
- **The `tools/__init__.py` adapter boilerplate, the regex PII and injection detectors, and the provider fallback design.** Unchanged from the W3 review.
- **No `docker compose` OTel collector.** `OTEL_TRACES_EXPORTER=console` and OTLP by environment are enough for now (ADR-0017).
