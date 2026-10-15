# W3 Review & Pre-W4 Plan

_Reviewed 2026-10-08 on branch `w3_review` (`main` @ `b45e619`, PR #32 merged). `make lint` is clean (ruff, ruff format, mypy strict over 151 files). `tests/unit` passes 299/299. Integration and e2e tests were not re-run in this review (they need Docker and API keys); I read them instead. This review changed no code._

---

## 1. Current Project State

**Architecture.** The feature-sliced layout from ADR-0002 holds. Nothing in `platform/` imports `features/` except `platform/mcp/server.py`, which is a composition root and allowed to. `domain/` imports nothing above it. The layering needs no reorganising.

**What runs today.**

- **`POST /claims/triage` and `/claims/triage/stream`** both run `run_triage()` or `stream_triage()` over one LangGraph graph: `call_model → dispatch_tools → … → finalize → (repair loop) → escalate`. The stages before the graph, in order:
  - injection detection, which escalates without calling the model;
  - PII redaction;
  - a `GuardedDispatcher` wrapped around `scope_for_agent`, which pins the server-issued `claim_id`.
- **`/approvals`** lists, approves and denies requests held by a module-level in-memory `ApprovalGate`.
- **RAG.** `search_kb` embeds the query (OpenAI) and searches pgvector with a relevance floor. `make ingest` loads the markdown seed documents, and `make eval` measures retrieval.
- **Persistence.** The Postgres pool, migration runner, `PostgresApprovalStore`, `PostgresClaimantFactsRepository`, `PgVectorStore` and the schema (`approval_requests`, `claims`, `long_term_memory`, `kb_chunks`) all exist and are integration-tested.
- **MCP.** The stdio server and a sync `McpToolClient` exist. `use_mcp` is available in `run_triage` but no endpoint uses it.
- **Docker.** `docker compose up` brings up the db, a one-shot migrate-and-ingest, and the API on :8000.

**Technologies.** Python 3.11, FastAPI with sync handlers, Pydantic v2 (frozen models), LangGraph, `anthropic`, `openai` (embeddings only), `mcp<2`, psycopg3 with pgvector, uv, ruff, mypy strict, pytest with pytest-asyncio, pre-commit. There is no CI.

**Still scaffold only, all W4 targets.** `platform/observability/{tracing,metrics}.py`, `platform/guardrails/policy_engine.py` and `policies/payout_approval.rego`, `platform/infrastructure/audit_repository.py`, and an empty `evals/datasets/airline_claims.jsonl`. Two scaffolds are not W4 targets: `platform/infrastructure/db_models.py` and `features/claims_triage/application/policies.py`. The two e2e test files are also docstring-only stubs.

**Overall.** The code is about 3.5k LOC in `src/` and strongly consistent: protocols at the seams, Pydantic at the boundaries, rules kept out of nodes, specific exception types, ADRs for the real decisions. W3's guardrail work (PII, injection) was built as decorators and entry-point checks, so it composes cleanly. **The structure is sound. There is one substantial gap, and it is semantic, not structural: the approval path was never finished** (F-01).

---

## 2. W3 Assessment

| W3 task | Implemented in | Verdict |
|---|---|---|
| Postgres + pgvector | `platform/infrastructure/{postgres,repositories,vector_store}.py`, `migrations/0001_init.sql` | ✅ Solid. Compare-and-set transitions, `ON CONFLICT` dedup, an advisory-locked migration runner, race tests. ⚠️ **Nothing consumes the approval store, the `claims` table or the executor seam.** The summary lists this as follow-up, and no W3 task picked it up |
| RAG pipeline | `rag/*`, `tools/search_kb.py`, `platform/ai/embeddings.py` | ✅ Clean. The `Embedder` and `VectorStore` protocols are injectable, the floor is documented in ADR-0012, and the lazy `default_retriever` keeps the registry buildable without a DB |
| Eval set | `evals/*` | ✅ The retrieval eval is well scoped and honest. ⚠️ There is no agent-level eval (F-07) |
| Docker Compose | `Dockerfile`, `docker-compose.yml`, `.dockerignore` | ✅ Multi-stage uv build, non-root user, health-gated start order, idempotent migrate-ingest. The single-replica constraint is documented |
| PII filtering | `guardrails/pii_filter.py`, `guarded_dispatcher.py`, `observability/logging.py` | ✅ Applied at the right seams (ADR-0013). A real bug (`record.args=None` breaking uvicorn's access log) was caught by the compose run and fixed with a regression test |
| Prompt-injection cases | `guardrails/injection_detection.py`, ADR-0014 | ✅ Honest about being heuristic and a single layer. ⚠️ Its escalation result breaks the documented shape of an escalated `TriageResult` (F-04) |
| `/triage` integration test | `tests/integration/api/test_triage_endpoint.py` | ✅ A real app, graph, tools, gate and pgvector with only the LLM scripted. ⚠️ It reaches into `approval_gate._GATE` with `monkeypatch`, a symptom of F-02 |

**Carry-over from the W2 review.** Of its W3 items, O-2 (delete the stubs) and O-3 (prompt v5) were done. **O-1 (build provider, stores and gate once in `create_app()` and inject them) was not**, and it is the root of the main finding.

**Consistency with AGENTS.md.** The code follows the rules. The docs have drifted from the code: the Layout section still lists `nodes/ (classify, retrieve, decide)` and the Commands section still has a "Planned: MCP standalone" line, although `python -m ombuds.platform.mcp.server` works. The README says a state-changing action "executes exactly once against a deterministic Postgres backend" (F-08).

---

## 3. Findings

### F-01 — The approval path is incomplete: in-memory gate, no executor, `claims` unused
- **Area:** Guardrails / persistence / governance
- **Current situation:**
  - `triage_use_case`, `log_claim`, `issue_payment` and `/approvals` all use `approval_gate._GATE`, an in-memory `ApprovalGate`.
  - `PostgresApprovalStore` is fully built and tested but not wired anywhere.
  - Nothing calls `claim_for_execution` (`grep` finds only definitions). Approving a request moves it `PENDING → APPROVED` and nothing happens next.
  - The `claims` table is never written, and `issue_payment` does not require a logged claim as ADR-0009 specifies.
  - A restart loses every pending approval. The MCP subprocess has its own separate gate.
  - `docker-compose.yml` and AGENTS.md work around this with "single replica only".
- **Problem / risk:**
  - The headline invariant ("approved → executed exactly once") is documented but unimplemented. A human clicking approve has no effect.
  - W4 builds directly on this path:
    - The audit trail ("every decision") needs durable approval and decision records.
    - The Rego "block auto-payout above €X" policy needs a payment action that something actually executes.
    - The `claims` and approval rows are the natural audit sources.
  - Building those on an in-memory, executor-less gate means building them twice.
- **Recommended change:**
  - Wire `PostgresApprovalStore` as the runtime store.
  - Add a small executor registry keyed by `GuardedAction`, run exactly once after an approval wins the `APPROVED → EXECUTED` transition.
  - `log_claim`'s executor writes the `claims` row, idempotent on `claim_id`.
  - `issue_payment`'s executor records the payout and requires a logged claim whose amount matches (ADR-0009). There is no real payment rail, so this is a simulated payout record, which needs migration `0002`.
  - Decide the transaction model (single transaction vs idempotent-write-then-claim) and record it as an ADR-0009 addendum.
- **Reason:** It closes the gap between what the project claims and what it does, and it is the foundation W4's audit and policy work sits on.
- **Priority:** Critical
- **Estimated complexity:** Large
- **Must fix before W4:** Yes

### F-02 — Module-level singletons instead of composition-root wiring (W2 O-1, still open)
- **Area:** Dependency management / testability
- **Current situation:**
  - The gate is a module global (`_GATE`) with free-function wrappers (`submit_for_approval` and friends).
  - Tools import `submit_for_approval` directly.
  - `default_retriever()` is an `lru_cache`d process-wide pool that is never closed.
  - `build_default_provider()` runs on every request.
  - `create_app()` builds no dependencies and has no lifespan.
  - Tests substitute the gate with `monkeypatch.setattr(approval_gate, "_GATE", …)`.
- **Problem / risk:**
  - F-01 cannot be done cleanly without choosing the store at the composition root. The API process and the MCP subprocess must be able to choose one the same way.
  - Pools are never closed or owned by anything.
  - Patching a private global is a smell the project's own code style argues against.
- **Recommended change:**
  - Give `build_tool_registry()` an `ApprovalStore` argument. It already does this for the retriever, via `retriever_factory`, so the pattern exists.
  - Build the pool and the store once in `create_app()` with a FastAPI lifespan that closes the pool. Expose them via `Depends` and `app.state`.
  - Make `/approvals` take the store from `Depends`.
  - Delete the module-level singleton and wrappers.
  - Keep `ApprovalGate` as the in-memory fake for unit tests.
  - Tests use `dependency_overrides` or pass a store in.
  - Do **not** add a DI container or framework.
- **Reason:** The smallest change that makes F-01 possible and removes the `_GATE` patching and the unowned pool.
- **Priority:** High
- **Estimated complexity:** Medium
- **Must fix before W4:** Yes

### F-03 — Approval endpoints are unauthenticated and `approver` is self-declared
- **Area:** Security / governance
- **Current situation:**
  - `/approvals/{id}/approve` accepts any caller and any free-text `approver`.
  - `docker compose up` publishes the API on `:8000`.
- **Problem / risk:** The human-in-the-loop control is only as strong as who can call it. Today anyone who can reach the port can approve a payout and attribute it to anyone. W4's audit trail would record an unverified identity.
- **Recommended change:**
  - Add one FastAPI dependency on the `/approvals` router that checks a bearer token from an environment variable.
  - Derive `approver` from the token's configured identity.
  - Do not build a user system.
- **Reason:** The audit trail is only meaningful if the actor field is trustworthy.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W4:** No. Do it inside the W4 audit-trail task, where the actor field is first consumed.

### F-04 — `run_triage` and `stream_triage` duplicate the run preamble, and the injection escalation breaks the escalation contract
- **Area:** Duplication / consistency
- **Current situation:**
  - Both functions repeat the same sequence: issue a `claim_id`, detect injection, redact, build the provider, load the prompt, build the guarded and scoped registry.
  - The injection escalation sets `answer=INJECTION_ESCALATION_REASON`. Every other escalation returns the fixed `ESCALATION_ANSWER`, which is what the `TriageResult` docstring promises.
- **Problem / risk:**
  - W4 must add a span, an audit write and a logged injection hit to **both** paths. Two copies invite drift. W2's F-07 was exactly this kind of stream/sync divergence.
  - Injection hits are currently untraceable: the escalation returns before anything records it.
- **Recommended change:**
  - Extract one private "prepare run" step that returns `(claim_id, claim_text, registry, system)`, or an early `TriageResult` for an injection.
  - Both entry points call it.
  - Use `ESCALATION_ANSWER` for the injection answer, keeping the specific text in `escalation_reason`.
  - Type `_to_result` and `_consolidate` with `AgentState` instead of `Mapping[str, Any]`.
- **Reason:** One place for W4 to attach tracing and audit, with no behaviour change except the one documented-contract fix.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W4:** Yes

### F-05 — Where W4 hooks in: the dispatcher decorator is the right seam, and no refactor is needed
- **Area:** Architecture (a positive finding, kept so nobody invents a task)
- **Current situation:**
  - `ToolDispatcher` is a protocol, and `GuardedDispatcher` and `_AgentScopedDispatcher` are decorators over it.
  - All tool calls, in-process and MCP alike, pass through `dispatch_all`.
  - The provider is likewise an `LLMProvider` protocol with a decorator (`FallbackProvider`).
- **Problem / risk:** None.
- **Recommended change:** None. W4 should add `TracingDispatcher` and `AuditingDispatcher` (and a tracing provider decorator) in this style rather than editing graph nodes.
- **Reason:** Recorded so the W4 plan reuses the existing pattern.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W4:** No

### F-06 — Stale and overstated documentation
- **Area:** Documentation
- **Current situation:**
  - AGENTS.md lists `nodes/ (classify, retrieve, decide, escalate_retry)`, but only `escalate_retry` exists. Its "Planned: MCP standalone" line is out of date.
  - The README claims exactly-once Postgres execution after approval. The README's flow also still starts with "classifies it".
  - `tasks.md` and the glossary will need W3 follow-ups updated.
- **Problem / risk:**
  - AGENTS.md is instruction input for future agent sessions, and the README is the interview artefact.
  - A wrong command or layout line is, per AGENTS.md's own words, "worse than no command".
  - The README is true only once F-01 lands.
- **Recommended change:** Fix AGENTS.md Layout and Commands, and reconcile the README against what runs. Do this **after** F-01 so it describes final behaviour.
- **Reason:** Cheap, and it prevents wrong guidance and overclaiming.
- **Priority:** Medium
- **Estimated complexity:** Small
- **Must fix before W4:** Yes (last step of the pre-W4 plan)

### F-07 — No agent-level eval, though prompts are meant to be gated on one
- **Area:** Testing / AI-project practice
- **Current situation:**
  - AGENTS.md says a new prompt version "must run clean against `evals/datasets/`".
  - `airline_claims.jsonl` is empty.
  - Only retrieval is evaluated. v4 went live without an end-to-end decision eval.
- **Problem / risk:**
  - Prompt and model changes are unmeasured, and W4's observability makes that gap more visible.
  - It does not block W4: the deterministic `verify_decision` guards correctness regardless.
- **Recommended change:**
  - A small dataset of claim text, expected eligibility and expected escalation, run against a real model on demand (`make eval`-style, never CI-failing).
  - Do this once W4's tracing can record the runs.
- **Reason:** It turns "prompt v5" from a guess into a measurement.
- **Priority:** Medium
- **Estimated complexity:** Medium
- **Must fix before W4:** No

### F-08 — Rego policy's threshold needs a single source of truth (W4 design note)
- **Area:** Governance / business rules
- **Current situation:**
  - `policy_engine.py` and `payout_approval.rego` are empty.
  - Code-style.md says business thresholds live only in `domain/` or `rules.py` and are never duplicated.
  - A Rego "€X" literal would be a second copy.
- **Problem / risk:** The threshold and the policy can drift apart.
- **Recommended change:** Pass X as OPA input data (config or constant) rather than hardcoding it in the `.rego` file. Evaluate the policy where F-01's executor and store meet (submit or approve), not inside tools.
- **Reason:** Cheap to get right on day one, awkward to unpick later.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W4:** No. Take it into W4 design.

### F-09 — Config is module-level env reads with no validation
- **Area:** Configuration
- **Current situation:**
  - `config.py` reads `os.environ` at import time and calls `load_dotenv()`.
  - A bad `ANTHROPIC_MAX_RETRIES=abc` fails at import with a bare `ValueError`.
  - The `embeddings` module reads its own defaults.
  - Tests that need different config monkeypatch module attributes.
- **Problem / risk:** Mild. W4 adds OTEL and auth settings, which will lengthen this file.
- **Recommended change:**
  - If, and only if, F-02 touches this anyway, switch to a frozen settings object built once in `create_app()`.
  - Otherwise leave it.
  - Do not add a settings library just for its own sake.
- **Reason:** Marginal today; useful once more settings arrive.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W4:** No

### F-10 — No CI
- **Area:** Developer experience / testing strategy
- **Current situation:** Quality gates are pre-commit only. The integration suite needs Docker and is easy to forget.
- **Problem / risk:**
  - Regressions in the integration suite go unnoticed.
  - For a showcase repo, a green badge is also part of the story.
- **Recommended change:** One GitHub Actions workflow: `make lint` plus `pytest tests/unit`, and a second job with a `pgvector/pgvector:pg16` service for `tests/integration`. Tests mock the LLM and embeddings, so no secrets are needed.
- **Reason:** About 30 lines for ongoing protection of W4's more invasive changes.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W4:** No

### F-11 — Dead scaffolds and small hygiene items
- **Area:** Maintainability
- **Current situation:**
  - `platform/infrastructure/db_models.py` and `application/policies.py` are one-line stubs with no planned owner. `tests/e2e/*` are docstring stubs.
  - The `scripts/compare_providers.py` docstring tells you to run `uv run --group scripts`, but `pyproject.toml` has no `scripts` group.
  - The `uv:latest` image in the Dockerfile is unpinned.
- **Problem / risk:** Minor confusion and a non-reproducible build.
- **Recommended change:** Delete `db_models.py` and `policies.py` unless W4 uses them. Fix or remove the script's run line. Pin the uv image tag. Leave the e2e stubs as the placeholder for the compose smoke test.
- **Reason:** Hygiene only.
- **Priority:** Low
- **Estimated complexity:** Small
- **Must fix before W4:** No

---

## 4. Required Refactoring Before W4

Only four tasks. Everything else in the review is optional or W4-scoped.

### P-1 — Composition-root wiring for the approval store, pool and registry (F-02)
- **Description:**
  - `build_tool_registry(approvals: ApprovalStore, retriever_factory=…)`.
  - `log_claim` and `issue_payment` take the store through the registry's closure.
  - `create_app()` builds the pool and `PostgresApprovalStore` once, with a lifespan that closes the pool.
  - `/approvals` and the triage routes get their dependencies via `Depends`.
  - Remove `_GATE` and the module-level wrapper functions.
  - The MCP `server.py` composition root builds the same Postgres-backed store, so both processes share it.
- **Files likely affected:** `api_app.py`, `platform/guardrails/{approval_gate,api}.py`, `features/claims_triage/tools/{__init__,log_claim,issue_payment}.py`, `application/triage_use_case.py` (accepts the registry or store), `api/routes.py`, `platform/mcp/server.py`, `config.py`, and the unit and integration tests that patch `_GATE`.
- **Reason:** Prerequisite for P-2, and it removes the unowned pool and global patching.
- **Acceptance criteria:**
  - `grep -rn "_GATE\|submit_for_approval" src` returns no module-level singleton.
  - Unit tests use `ApprovalGate()` instances or `dependency_overrides`, with no private patching.
  - The pool is closed on app shutdown.
  - The API and the MCP subprocess both use the Postgres store.
  - All existing tests pass unchanged in behaviour.
  - `make lint` is clean.
- **Dependencies:** None.

### P-2 — Executors, durable claims, and a payment record (F-01)
- **Description:**
  - An executor registry keyed by `GuardedAction`, called once after a request wins `claim_for_execution`.
  - `log_claim`'s executor writes `claims` (idempotent on `claim_id`).
  - `issue_payment` requires an existing logged claim whose recorded amount matches the request payload. Its executor records the payout in a new `payments` table (migration `0002`, idempotent on `claim_id`).
  - Add an ADR-0009 addendum stating the transaction model and that no real payment rail exists.
- **Files likely affected:** `platform/guardrails/{approval_gate,api}.py`, `platform/infrastructure/{repositories,migrations/0002_*.sql}`, `features/claims_triage/tools/{log_claim,issue_payment}.py`, a small feature-side executor module, `docs/decisions/0009-*.md`, and unit and integration tests.
- **Reason:** Delivers the "approved → executed exactly once" invariant that the README, ADR-0009 and AGENTS.md assert, and gives W4's audit trail and Rego policy a real action to govern.
- **Acceptance criteria:**
  - Approving a `log_claim` request produces exactly one `claims` row; a second approve or claim attempt raises `ApprovalStateError` and writes nothing.
  - `issue_payment` for an unlogged claim, or for a mismatched amount, is rejected as a `ToolExecutionError`.
  - Concurrent approvals produce exactly one execution (an integration test, like the existing race tests).
  - Pending and approved requests survive an API restart.
  - The tool-callable invariant stays true: no tool executes inline.
  - The agent's tool set (`AGENT_TOOL_NAMES`) is unchanged, so `issue_payment` is still not offered to the agent.
- **Dependencies:** P-1.

### P-3 — One shared triage-run preamble and consistent escalation shape (F-04)
- **Description:**
  - Extract the duplicated setup in `run_triage` and `stream_triage` into one helper.
  - The injection escalation returns `ESCALATION_ANSWER` as `answer`, and the specific text only in `escalation_reason`.
  - Type `_to_result` and `_consolidate` with `AgentState`.
- **Files likely affected:** `application/triage_use_case.py`, its unit tests, and `tests/integration/api/test_triage_endpoint.py` if it asserts the injection `answer` text.
- **Reason:** The single place for W4 to attach tracing and audit for both endpoints, and it fixes a contract inconsistency.
- **Acceptance criteria:**
  - `run_triage` and `stream_triage` contain no duplicated setup.
  - The existing parity tests pass.
  - An injection escalation's `answer` equals `ESCALATION_ANSWER`.
  - `mypy` reports no `Any` in those two helpers.
- **Dependencies:** None. It can run in parallel with P-1, but doing it after P-2 avoids merge churn in the same file.

### P-4 — Documentation reconciliation (F-06)
- **Description:**
  - Fix the AGENTS.md Layout (nodes) and Commands ("Planned" line, the approval store, "single replica" note).
  - Reconcile the README with actual behaviour.
  - Update `tasks.md` and the glossary.
  - Add the W3 review follow-ups to `task_summaries.md`.
- **Files likely affected:** `AGENTS.md`, `README.md`, `docs/progress/*`.
- **Reason:** Written last so it describes the final behaviour.
- **Acceptance criteria:**
  - Every command in AGENTS.md is verified to run.
  - The README makes no claim the code doesn't back.
  - The "single API replica" constraint is removed, or re-justified if something else still requires it.
- **Dependencies:** P-1, P-2, P-3.

---

## 5. Optional Improvements

Useful, but none should block W4.

| ID | Improvement | When |
|---|---|---|
| F-03 | Bearer-token dependency on `/approvals`, with `approver` taken from the token | Inside the W4 audit-trail task |
| F-05 | Add `TracingDispatcher`, `AuditingDispatcher` and a tracing provider decorator in the existing decorator style (no node edits) | The W4 tracing and audit tasks |
| F-08 | Pass the payout threshold into OPA as input data, not a Rego literal | The W4 Rego task |
| F-07 | Agent-level eval dataset (`airline_claims.jsonl`) before the next prompt version | After W4 tracing, so the runs are recorded |
| F-10 | One GitHub Actions workflow (lint and unit; integration with a pgvector service) | Any time; it helps most before W4's bigger changes |
| F-09 | Frozen settings object, only if P-1 already touches `config.py` | Opportunistic |
| F-11 | Delete the two dead stubs, fix the script's `--group` line, pin the uv image tag | Opportunistic |

---

## 6. Proposed Pre-W4 Execution Plan

- [ ] **P-1** — Composition-root wiring: store, pool and registry injected, `_GATE` removed
- [ ] **P-2** — Executors, durable `claims`, `payments` migration, ADR-0009 addendum
- [ ] **P-3** — Shared triage-run preamble, consistent escalation `answer`
- [ ] **P-4** — Docs reconciliation (AGENTS.md, README, tasks, summaries)

Commit each task separately, per the project's one-commit-per-task habit. Estimated effort is P-1 about half a day, P-2 one to two days, and P-3 and P-4 an hour or two each.

---

## 7. Final Recommendation

**Ready for W4 after the required refactoring.**

The codebase is well structured, consistent and well tested (lint and types are clean, 299 unit tests pass), and the layering, the protocol seams and the guardrail decorators are the right shape. W4's tracing and audit can be added as more decorators without redesign. Nothing needs rewriting.

What blocks W4 is one unfinished piece of W3 rather than a design flaw. The approval gate is in-memory and process-global, and nothing executes an approved request, even though the Postgres store, the `claims` table and ADR-0009 all assume it does. W4's audit trail and Rego payout policy both attach to exactly this path. They would be built on a gate that forgets everything on restart and an action nothing performs.

P-1 and P-2 fix that, P-3 gives W4 a single place to attach tracing and audit, and P-4 makes the docs match the result. Everything else in this review is optional.

**Considered and left alone:**
- **Sync handlers.** Async migration is not warranted: the work is blocking SDK calls, and FastAPI runs sync handlers in a threadpool.
- **The `tools/__init__.py` adapter boilerplate.** It is repetitive but explicit, and four tools do not justify a generic helper.
- **Regex PII and injection detectors.** Their limits are documented in ADR-0013 and ADR-0014, and the approval gate and tool scoping hold regardless.
- **The provider fallback design.** It is consistent with ADR-0006.
