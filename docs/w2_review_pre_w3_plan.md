# W2 Review & Pre-W3 Plan

_Reviewed 2026-09-28 on branch `w2_final_review` (`main` @ `0568d11`, PR #20 merged, plus one docs-only commit). `make test` passes: ruff clean, mypy strict clean, 132/132 unit tests. `pytest tests/integration` passes 3/3 (the real MCP subprocess round-trip)._

---

## 1. Current Project State

**Architecture.** The feature-sliced layout from ADR-0002 still holds. `grep -r "ombuds.features" src/ombuds/platform` finds only `platform/mcp/server.py`, which is a composition root and is allowed to import features (ADR-0003 as amended in pre-W2 T-5). Nothing in `domain/` imports anything above it.

**What runs today.**

- **`POST /claims/triage`**: `run_triage()` compiles a LangGraph `StateGraph` with four nodes:
  - `call_model` → `dispatch_tools` → back to `call_model`, or
  - `call_model` → `finalize`, which either returns or loops back with a repair message, or
  - → `escalate`, which ends the run without a verified decision.

  Tools come from an in-process `ToolRegistry`. The optional `use_mcp=True` path uses a real MCP subprocess instead; no caller uses it yet.
- **`POST /claims/triage/stream`**: `stream_triage()` is still the **W1 hand-written loop**, not the graph.
- **`GET /approvals`, `POST /approvals/{id}/approve|deny`**: resolve requests held in an in-memory `ApprovalGate`. It is a module-level singleton.
- **MCP**: `python -m ombuds.platform.mcp.server` serves all four tools over stdio. `McpToolClient` is a sync facade over an anyio blocking portal.
- **Memory**: `ShortTermMemory` lasts one run and is injected into the system prompt every turn. `LongTermMemory` plus an `InMemoryLongTermMemoryStore` persist across runs, but are not wired to the API.
- **Tools**:
  - `check_eligibility`: real, delegates to `rules.py`.
  - `log_claim`: gated by approval, recomputes eligibility itself.
  - `issue_payment`: gated by approval.
  - `search_kb`: always raises `ToolExecutionError`, since the RAG layer is not built.

**Technologies.** Python 3.11, FastAPI (sync handlers), Pydantic v2 (frozen models by default), `anthropic` SDK, LangGraph, `mcp<2`, anyio, uv, ruff, mypy `--strict`, pytest with pytest-asyncio, pre-commit. There is no CI.

**Still scaffold only (one-line docstring files).** These are expected at this stage, not debt:

- RAG: `rag/*`
- infrastructure: `platform/infrastructure/*`
- observability: `platform/observability/*`
- guardrails: `pii_filter`, `injection_detection`, `policy_engine`
- agent nodes: `nodes/classify|retrieve|decide`
- evals: `evals/run_evals.py`, and `evals/datasets/airline_claims.jsonl`, which is empty
- `docker-compose.yml` and the e2e tests

**Overall.** The code is small (~2.1k LOC in `src/`), consistent and well tested, and it still reads as one person's disciplined design. The W1 pre-W2 hardening landed properly: the provider error classification, the `ToolExecutionError` contract, the tool catalogue's new home, and `verify_decision`.

**The structure does not need reorganising.** The W2 problems are in the **semantics of the governance path**, not in the layering:

- what an escalated run returns;
- what an approval actually authorises;
- who authors `claim_id` and `amount_eur`;
- what memory is allowed to inject into the system prompt;
- one public endpoint that skips all of the above.

These matter now because W3 builds persistence, RAG and guardrails directly on top of them.

---

## 2. W2 Assessment

| W2 task | Implemented in | Verdict |
|---|---|---|
| Rebuild tool-calling loop in LangGraph | `agent/graph.py`, `agent/state.py`, `triage_use_case.py` | ✅ The graph is clean, bounded, and passes the W1 test suite unchanged. ⚠️ Two W1 review items were made acceptance criteria of this task and were **not** done: stream/sync parity (W1 F-07 → F-07 below) and building the provider once at the composition root (W1 F-13 → F-08) |
| Stand up MCP server | `platform/mcp/server.py`, `tool_bindings.py`, `tools/search_kb.py`, `tools/issue_payment.py` | ✅ It follows ADR-0003 as amended: there is one schema per tool, `server.py` is the only feature import, and the protocol is tested in memory. Honest stubs rather than fake results |
| Connect LangGraph agent to tools over MCP | `platform/mcp/client.py`, `ToolDispatcher` protocol, `ToolDefinition.raw_schema` | ✅ The `ToolDispatcher` protocol is the right seam and the portal bridge is careful. ⚠️ Opt-in only and tested only at integration level. Its approval gate lives in a separate process from the HTTP approvals API (F-05) |
| Short-term + long-term memory | `agent/memory/*`, `graph.py` `_augmented_system` | ⚠️ The mechanics are clean (frozen models, a store protocol). But short-term memory copies raw tool output into the **system prompt**, and long-term memory saves the **model's free-text explanation** and replays it into future system prompts (F-06) |
| Escalation/retry on low confidence | `nodes/escalate_retry.py`, `graph.py` routing | ✅ The right call: escalation is a business outcome in state, not an exception. ❌ An escalated run returns the **rejected, rules-contradicting verdict text** as `answer` (F-01). Verified: a persistent-mismatch run returns `answer='{"eligible": true, "compensation_amount_eur": 999, …}'` |
| Human-approval gate (+ "idempotent on `claim_id`") | `platform/guardrails/approval_gate.py`, `api.py`, ADR-0008 | ⚠️ The deny-by-default blocking works, and fails closed. ❌ An approval is **reusable forever** (verified: three checks after one approval all return `approved=True`). It is keyed on a **model-invented `claim_id`**, and not bound to what the human looked at. Nothing leads from "approved" to "executed" (F-02 to F-05). The idempotency requirement was deferred, and the deferral is documented |

**Consistency with project standards.** High for style: docstrings, frozen models, `StrEnum`, one test module per source module, no `except Exception`, and error translation at the boundary. The deviations that matter are **semantic**:

- **README's core claim, "the LLM never becomes the source of truth for the claim's outcome"**, is enforced in `finalize`/`verify_decision`. It is bypassed in three places:
  - the escalation `answer` (F-01);
  - `issue_payment.amount_eur` (F-04);
  - `/triage/stream` (F-07).
- **README step 6, "Executes only after approval"**: no approval-to-execution path exists yet (F-05).
- **ADR-0008 names its own trigger for revisiting ("multiple processes")**, and W2's own MCP work has already hit it (F-05).
- **`code-style.md`: "Models are frozen by default"**: `ApprovalRequest` is mutable and is mutated in place, shared with API readers (F-02).

**Intended vs. actual.** Every W2 checkbox has working, tested code behind it. What was deferred:

- stream parity and provider DI (both flagged in W1);
- `claim_id` idempotency, explicitly deferred to W3;
- any path from an approval to execution, which is implicit and not written down anywhere.

---

## 3. Findings

Ordered by priority, then by dependency.

### F-01: An escalated run returns the rejected, unverified verdict as the passenger-facing `answer`
- **Area:** Domain correctness / governance
- **Current situation:** `escalate()` sets `answer = state["text"] or <fallback message>` ([escalate_retry.py:20](../src/ombuds/features/claims_triage/agent/nodes/escalate_retry.py#L20)). `state["text"]` is the last model turn, so it contains:
  - **after repair exhaustion** ([graph.py:118-123](../src/ombuds/features/claims_triage/agent/graph.py#L118-L123)): the verdict JSON that `verify_decision` just **rejected**, because it contradicts `check_eligibility`;
  - **after `MAX_TOOL_TURNS`** ([graph.py:72-76](../src/ombuds/features/claims_triage/agent/graph.py#L72-L76)): stale text from an earlier tool-use turn, e.g. "Let me check…";
  - **after `stop_reason="max_tokens"`**: a truncated reply.

  The escalation tests assert `escalated`, `decision is None` and `escalation_reason`, but **never `answer`**.
- **Problem / risk:** `POST /claims/triage` returns `{"escalated": true, "decision": null, "answer": "{\"eligible\": true, \"compensation_amount_eur\": 999, …}"}`. That is a model-authored eligibility and amount which the rules engine contradicted, delivered as the text a client will show to a passenger. It is the exact failure F-01 in W1 fixed on the success path.
- **Recommended change:** When a run is escalated, `answer` is always the fixed human-review message. Keep the model's last text out of `answer`. If it is useful for debugging, put it in `escalation_reason`, or keep it for the W4 audit trail.
- **Reason:** A one-line fix that restores the project's core invariant on the one exit path the invariant doesn't yet cover.
- **Priority:** High · **Complexity:** Small · **Must fix before W3:** Yes

### F-02: An approval is reusable forever and isn't bound to what the human approved
- **Area:** Governance / security / data model
- **Current situation:**
  - `ApprovalGate.check` returns `approved=True` every time it sees an `APPROVED` request ([approval_gate.py:88-89](../src/ombuds/platform/guardrails/approval_gate.py#L88-L89)). Nothing consumes an approval. Verified: one approval, then three checks, all `True`.
  - `log_claim`'s approval context is `{"claim_id": …}` only ([log_claim.py:53](../src/ombuds/features/claims_triage/tools/log_claim.py#L53)). The approver sees a bare id: no facts, no computed eligibility, no amount. The eligibility is computed one line earlier and then discarded. A later `log_claim` for the same `claim_id` with **different facts** matches the same approved request.
  - `check_approval(action, context=None)` falls back to `{}` ([approval_gate.py:133-135](../src/ombuds/platform/guardrails/approval_gate.py#L133-L135)). Approving one request with an empty context would approve every future context-less call for that action.
  - `ApprovalRequest` is `frozen=False` and mutated in place under the lock ([approval_gate.py:36](../src/ombuds/platform/guardrails/approval_gate.py#L36), [119-127](../src/ombuds/platform/guardrails/approval_gate.py#L119-L127)). But `check()` reads `status` **outside** the lock, and `list_pending()` hands the same mutable objects to the API serializer.
- **Problem / risk:** This is latent today, because both approved branches raise "not implemented". W3 writes the persistence behind those branches, and at that point **one human approval authorises unlimited executions**, including ones with facts the human never saw. That is the double-log/double-pay case the W2 task text (W1 F-04) said must not happen. The Postgres schema W3 designs for approvals will also copy whatever these semantics are.
- **Recommended change:**
  1. **Single-use.** Checking an approved request transitions it atomically, under the lock, to a terminal `CONSUMED` state (the name is your call), and it is returned as approved once. In W3 the transition and the persistence write share one DB transaction.
  2. **Bind the approval to the payload.** The context is the rules-derived payload the human is actually approving:
     - `log_claim`: `claim_id`, `eligible`, `compensation_eur`, `reasons`, and a stable digest of the `FlightDisruption` facts;
     - `issue_payment`: `claim_id` and the rules-derived amount (see F-04).

     Changing the facts then produces a new request.
  3. **Context is required and non-empty.** Drop the `None → {}` default.
  4. **Frozen `ApprovalRequest`.** Replace it with `model_copy(update=…)` under the lock, and read the status under the lock.
- **Reason:** The gate is the "one thing not to relax" in AGENTS.md. Its semantics have to be right *before* W3 makes the approved branch real and builds a schema on it.
- **Priority:** Critical · **Complexity:** Medium · **Must fix before W3:** Yes

### F-03: `claim_id` is invented by the model
- **Area:** Identity / API design
- **Current situation:**
  - `TriageRequest` has only `claim_text` ([schemas.py:9-14](../src/ombuds/features/claims_triage/api/schemas.py#L9-L14)).
  - `LogClaimArgs.claim_id` and `IssuePaymentArgs.claim_id` are tool arguments the LLM fills in. Nothing issues, validates or scopes them.
- **Problem / risk:**
  - The approval dedup key, the future idempotency key and the future `claims` primary key are all whatever string the model chose.
  - Two unrelated runs can pick the same id, for example `"CLM-001"`, and share an approval.
  - A claim text containing "use claim_id X" steers which approval gets reused.
  - The ADR-0008 flow ("the next call with the same context sees the resolution") needs a later run to reproduce the same invented id, which in practice it won't.
- **Recommended change:**
  - The server owns `claim_id`. `run_triage` accepts one, or generates a UUID, and returns it on `TriageResult`/`TriageResponse`.
  - In the in-process path, build the registry per run with that id bound, e.g. `build_tool_registry(claim_id=…)`, so that the state-changing tools either:
    - take `claim_id` from the binding, or
    - reject an argument that doesn't match it, with `ToolExecutionError`.
  - The MCP server has no run context. There, validating `claim_id` against the `claims` table is part of W3's Postgres work, so note it in the ADR (F-05).
- **Reason:** Every W3 persistence and idempotency decision keys on this identifier, so it has to be trustworthy first.
- **Priority:** High · **Complexity:** Small–Medium · **Must fix before W3:** Yes

### F-04: `issue_payment.amount_eur` is authored by the LLM, which regresses W1 F-01 on the money path
- **Area:** Domain correctness / governance
- **Current situation:** `log_claim` recomputes eligibility from the facts (the pre-W2 T-6 fix). `issue_payment`, added in W2, takes `amount_eur: int` directly from the model ([issue_payment.py:16](../src/ombuds/features/claims_triage/tools/issue_payment.py#L16)) and puts it into the approval context. Nothing checks it against `rules.evaluate()`. Nothing requires the claim to have been logged first either, although the docstring says "for an already-logged claim".
- **Problem / risk:** The human approver is shown a model-typed number as the payout, which is the exact scenario W1 F-01 described. The prompt (v4) doesn't mention `issue_payment` at all, yet the tool is offered to the model on every turn (see F-09).
- **Recommended change:** Mirror `log_claim` until persistence exists: `IssuePaymentArgs` = `claim_id` + `FlightDisruption`, and the amount comes from `evaluate()`. Once W3 has a `claims` table, the amount comes from the logged claim record, and a payment requires one. Whether the triage agent should be offered `issue_payment` at all belongs to the F-05 decision.
- **Priority:** High · **Complexity:** Small · **Must fix before W3:** Yes

### F-05: There's no approval-to-execution path, and the in-memory gate is already split across processes
- **Area:** Architecture / ADR-0008
- **Current situation:**
  - ADR-0008 says an approval "arrives the next time the same claim is retried through the loop". But nothing retries it: the run that hit the gate has ended. A new run would have to re-invent the same `claim_id` and the same context (F-03).
  - README step 6, "Executes only after approval, through tools exposed over MCP", has no implementation path.
  - `_GATE` is per process. With `use_mcp=True`, `check_approval` runs in the MCP **subprocess**, whose gate is invisible to `/approvals` and disappears when the run ends. So on the MCP path an approval can never be granted. It fails closed, which is safe, but broken.
  - ADR-0008's own revisit trigger, "multiple processes", has therefore already been hit.
  - README #5 says "Low-risk actions (logging) auto-execute", but the code requires a human for `log_claim`. That decision is for the W4 policy engine, but the ADR should record the intended end state.
- **Problem / risk:** W3's Postgres task will design the approval and claims tables. Without a decided execution model, it will either persist today's semantics as they are, or design around an unstated assumption.
- **Recommended change:** Amend ADR-0008, or supersede it with ADR-0009. **Decide:**
  - **(a) Recommended: the approval request *is* the pending action.** It stores the validated, rules-derived payload (F-02). Approving it hands that payload to a registered executor, which runs it **exactly once**, idempotent on the request id plus `claim_id`. The LLM is not re-invoked to "retry".

    This matches the original domain design (`domain/models/claim.py`'s docstring still lists `ProposedAction`) and README's "writing to a deterministic Postgres backend that the LLM never owns". It also works the same for the in-process and MCP paths.
  - **(b) LangGraph `interrupt()` plus a checkpointer**, resumed with `Command(resume=…)`. It is idiomatic for LangGraph, but the interrupt has to happen in a graph node rather than inside a tool handler, so it doesn't cover external MCP clients. It also ties approvals to graph checkpoints.

  Also record:
  - the store must be shared, i.e. Postgres in W3, and why (the MCP process split);
  - which tools the triage agent is offered;
  - whether `log_claim` is meant to auto-run under the W4 policy.

  **Pre-W3 scope is the decision only.** The executor and the Postgres store are W3 implementation.
- **Priority:** High · **Complexity:** Small (decision + ADR) · **Must fix before W3:** Yes (the decision); No (the implementation)

### F-06: Memory promotes tool output and model-written text into the system prompt
- **Area:** AI security / prompt design
- **Current situation:**
  - `dispatch_tools` copies every successful tool result's raw `content` into `short_term` ([graph.py:101-104](../src/ombuds/features/claims_triage/agent/graph.py#L101-L104)).
  - `_augmented_system` appends it to the **system prompt** every turn ([graph.py:49-52](../src/ombuds/features/claims_triage/agent/graph.py#L49-L52)).
  - The same results are already in `messages` as `tool_result` blocks, so each result is sent twice per turn.
  - Long-term memory saves `decision.explanation`, which is free text the model wrote from a passenger's claim text ([triage_use_case.py:124](../src/ombuds/features/claims_triage/application/triage_use_case.py#L124)), and replays it into the **system prompt** of every later run for that claimant.
- **Problem / risk:** Today the only remembered result is `check_eligibility`'s, which is trusted rules output, so it's harmless. W3 makes `search_kb` real: retrieved document snippets will then be raised from tool-result trust to **system-prompt trust**, and a passenger's claim text gains a path, via the explanation, into a *future* run's system prompt (persistent injection).

  This lands in the same week as W3's "prompt-injection test cases" task. A system prompt that changes every turn also rules out prompt caching of the tools + system prefix later.
- **Recommended change:**
  - **Short-term:** stop mirroring raw tool results. If a restatement adds value, render only typed, trusted facts produced by our code, e.g. the latest `EligibilityResult` fields, or drop short-term memory injection entirely, since `messages` already carries the results.
  - **Long-term:** store structured, rules-derived facts (`claim_id`, `eligible`, `compensation_eur`, `reasons`), not model prose.
  - Put any memory that stays in a user-turn context block, not in the system prompt.
- **Reason:** A small change now. Afterwards it would be a retrofit on top of RAG and a persisted memory schema.
- **Priority:** High · **Complexity:** Small · **Must fix before W3:** Yes

### F-07: `/claims/triage/stream` bypasses the graph: no verification, no escalation, and it raises on non-convergence
- **Area:** API consistency / governance
- **Current situation:** `stream_triage` ([triage_use_case.py:128-158](../src/ombuds/features/claims_triage/application/triage_use_case.py#L128-L158)) is the W1 loop. It has:
  - no `verify_decision` and no repair;
  - no escalation;
  - no `stop_reason` handling;
  - `raise RuntimeError` after `MAX_TOOL_TURNS`, and a mid-stream failure just closes the SSE stream without an error frame.

  The client gets the model's raw verdict JSON inside `turn_done.text`. This was W1 F-07, made an acceptance criterion of the LangGraph rebuild, and deferred again in W2.
- **Problem / risk:**
  - A public endpoint returns verdicts the rules engine never checked, which is the core invariant again.
  - Every W3/W4 guardrail (PII output filtering, injection handling, audit, tracing) would have to be built twice or would skip this path.
  - W3's "`/triage` end-to-end integration test" would test only one of the two paths.
- **Recommended change:** Serve both endpoints from one graph:
  - `call_model` uses `provider.stream_turn()` and forwards `TextDelta`/`ToolCallDelta` through LangGraph's `get_stream_writer()`;
  - `stream_triage` iterates `app.stream(…, stream_mode=["custom", "values"])`;
  - it finishes with one `final` SSE frame carrying `decision` / `escalated` / `escalation_reason` / `answer`, the same fields as `TriageResponse`, plus an `error` frame on failure.

  **Acceptable time-boxed alternative:** remove `/triage/stream` until it can run on the graph, and note it in ADR-0007. Either way, there must be no unverified path.
- **Priority:** High · **Complexity:** Medium (Small if removed) · **Must fix before W3:** Yes

### F-08: Wiring is per request and global rather than at the composition root
- **Area:** Dependency injection / resource use
- **Current situation:**
  - `run_triage` builds a new `FallbackProvider` (two `anthropic.Anthropic` clients, i.e. two connection pools) and **recompiles the graph** on every request ([triage_use_case.py:77](../src/ombuds/features/claims_triage/application/triage_use_case.py#L77), [95](../src/ombuds/features/claims_triage/application/triage_use_case.py#L95)).
  - The approval gate is a module-level `_GATE`.
  - `LongTermMemoryStore` has no production wiring.
  - Route tests monkeypatch module attributes.
- **Problem / risk:** W3 replaces `_GATE` and the memory store with Postgres-backed ones, and adds a DB pool. With today's wiring, that swap means patching module globals, or opening a connection per request.
- **Recommended change:**
  - `create_app()` builds the provider, the approval store and the memory store once, and exposes them through `Depends`.
  - `run_triage` takes them as required arguments.
  - Tools receive the gate through `build_tool_registry(…)`, the same per-run binding as F-03.
  - Tests use `app.dependency_overrides`.
- **Reason:** Real, but its concrete consumer is W3's Postgres task. Doing it as that task's first step avoids designing the DI shape twice.
- **Priority:** Medium · **Complexity:** Small–Medium · **Must fix before W3:** No (first step of W3 "Set up Postgres")

### F-09: The tool catalogue offered to the model has drifted from the prompt
- **Area:** Prompt / tool design
- **Current situation:**
  - Every turn offers four tools. Prompt v4 describes only `check_eligibility` and `log_claim`.
  - `search_kb` always errors, so any call to it burns one of the 8 turns and pushes the run toward escalation.
  - `issue_payment` is offered with no guidance at all.
- **Recommended change:** Handle this as part of W3's RAG task:
  - `search_kb` becomes real;
  - prompt v5 covers the full catalogue that F-05 decides the agent is offered;
  - v5 goes live only after the W3 eval set exists, which is the AGENTS.md gate that v3 and v4 both skipped.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W3:** No (W3 RAG task)

### F-10: RAG has two stubbed entry points (`search_kb` tool vs `nodes/retrieve.py`)
- **Area:** Architecture / avoiding duplicate work
- **Current situation:** Retrieval can be reached either through the agent-invoked `search_kb` tool (built, with a schema, exposed over MCP) or through the stub `agent/nodes/retrieve.py`. The `classify` and `decide` stubs predate the tool-loop graph and are unused.
- **Recommended change:** At the start of the W3 RAG task, pick one and delete the other stub. I recommend `search_kb` as the single retrieval entry point, since it is already on MCP and the schema is tested. Delete the `classify`/`decide` stubs too, unless W3/W4 has a concrete use for them.
- **Priority:** Medium · **Complexity:** Small (decision) · **Must fix before W3:** No (W3 RAG kickoff)

### F-11: The tests missing are exactly the ones that would have caught F-01 and F-02
- **Area:** Testing
- **Current situation:**
  - No test asserts `answer` on an escalated run.
  - No test covers approval reuse, payload binding or empty context.
  - No graph-level test covers `log_claim` denied → model loops → escalation or a clarifying answer.
  - `tests/integration/` is outside `make test`, and there is no CI, only pre-commit, which runs unit tests locally.
  - W1 hygiene leftovers: the empty `test_eu261_rules.py` and the empty `tests/unit/features/claims_triage/guardrails/` package.
- **Recommended change:** The behavioural tests ship with T-1, T-4 and T-6 below. Add a `make test-integration` target, plus a minimal GitHub Actions job running `make test`, when W3's Docker-backed integration tests arrive. Delete the two empty placeholders.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W3:** Only the tests attached to the required tasks

### F-12: `MAX_TOKENS = 1024` is hardcoded, and truncation now means escalation
- **Area:** LLM integration
- **Current situation:** `MAX_TOKENS = 1024` is set in [anthropic.py:13](../src/ombuds/platform/ai/providers/anthropic.py#L13). Since W2, `stop_reason="max_tokens"` routes to `escalate`, so a long explanation now becomes a human-review ticket rather than a truncated answer. W1 O-4 asked for this to be configurable during the W2 loop rebuild.
- **Recommended change:** Add `ANTHROPIC_MAX_TOKENS` to config and `.env.example`, with a 4096 default.
- **Priority:** Low · **Complexity:** Small · **Must fix before W3:** No

### F-13: The HTTP surface has no authentication
- **Area:** Security
- **Current situation:** Anyone who can reach the app can approve payouts (`approver` is free text) or run triage, which costs tokens. ADR-0008 acknowledges this for the demo.
- **Recommended change:** Nothing in code before W3. When W3 writes `docker-compose.yml`, bind the API port to `127.0.0.1`. Put at least a shared-secret header on `/approvals/*` before any non-local deployment.
- **Priority:** Medium · **Complexity:** Small · **Must fix before W3:** No

### F-14: Hygiene carried over
- **Area:** Maintainability
- **Items** (about 30 minutes in total, any time):
  - The `FallbackProvider` docstring still says primary and fallback "may be entirely different SDKs". The message history is Anthropic-shaped, so they can't be (W1 F-08) ([fallback.py:3](../src/ombuds/platform/ai/providers/fallback.py#L3)).
  - `openai` is still a runtime dependency, but only `scripts/compare_providers.py` uses it. Move it to a `scripts` dependency group.
  - `claim_text` has no `max_length`, so the token cost of one request has no ceiling.
  - If `McpToolClient.__enter__` fails to connect, it leaves the portal thread running ([client.py:71-76](../src/ombuds/platform/mcp/client.py#L71-L76)).
  - Commit `1c0ea0b`, "Implement feature X to enhance user experience…", is a docs-only commit with a placeholder message. Reword it before merging `w2_final_review`.
- **Priority:** Low · **Complexity:** Small · **Must fix before W3:** No

### Deliberately *not* raised
- **`agent/` imports `application/decision.py`, and `application/` imports `agent/`.** This is not a module cycle, both are inside one feature, and moving `TriageDecision` would only be churn.
- **The tool-loop nodes live inline in `graph.py`** rather than in `nodes/`. It's a closure over provider and registry, it's readable, and it has one consumer.
- **The sync graph with an anyio portal for MCP.** Correct and contained. Going async gives no benefit until there's a concurrency requirement.
- **In-memory stores as such.** They are accepted by ADR-0008. The problem is their *semantics* (F-02, F-05), not the fact that they're in memory.
- **`TypedDict` state and the `recursion_limit` formula.** Idiomatic LangGraph, and the formula is bounded.
- **`config.py` import-time `load_dotenv`.** Move to `pydantic-settings` as part of W3's Postgres task, when `DATABASE_URL` actually arrives, as W1 said. Not before.
- **Missing evals.** A W3 task already covers this. F-09 ties the next prompt bump to it.

---

## 4. Required Refactoring Before W3

Listed in implementation order. T-1 and T-5 are independent and can go first or in parallel.

### T-1: Escalation never returns an unverified verdict (F-01)
- **Files:** `agent/nodes/escalate_retry.py`, `tests/unit/features/claims_triage/application/test_triage_use_case.py`
- **Reason:** It closes the last `/triage` exit path where model-authored eligibility or amount reaches the caller.
- **Acceptance criteria:**
  - For every escalation cause (repair exhaustion, verification mismatch, `MAX_TOOL_TURNS`, unrecoverable `stop_reason`), `answer` is the fixed human-review message and contains none of the model's final text.
  - The existing escalation tests assert on `answer`. The persistent-mismatch test asserts that `"999"` does not appear in it.
- **Depends on:** nothing

### T-2: Decide the approval-to-execution model (F-05)
- **Files:** `docs/decisions/0008-in-memory-poll-based-human-approval.md` (amend), or a new `0009-…` that supersedes it; `AGENTS.md` if the guardrails wording changes
- **Reason:** W3's Postgres schema and T-3/T-4 depend on it.
- **Acceptance criteria:** The ADR records:
  - the execution model, (a) or (b) from F-05;
  - that approvals are single-use and bound to the payload;
  - that `claim_id` is server-issued;
  - that the store must be shared (Postgres, W3), and why (the MCP subprocess split);
  - which tools the triage agent is offered;
  - the intended W4 policy for `log_claim` (auto vs human), reconciled with README #5.
- **Depends on:** nothing

### T-3: A server-issued `claim_id` (F-03)
- **Files:** `api/schemas.py`, `api/routes.py`, `application/triage_use_case.py`, `tools/__init__.py` (`build_tool_registry` binding), `tools/log_claim.py`, `tools/issue_payment.py`, and their tests
- **Reason:** The approval, idempotency and persistence keys must not be LLM-authored.
- **Acceptance criteria:**
  - `run_triage` takes an optional `claim_id`, generates a UUID if it's missing, and returns it on `TriageResult`/`TriageResponse`.
  - In the in-process path, a state-changing tool call whose `claim_id` differs from the run's comes back as an `is_error` `ToolResult`, or the argument is removed and bound instead (per T-2).
  - A test shows a model-supplied foreign `claim_id` cannot reach `check_approval`.
- **Depends on:** T-2

### T-4: Approval gate semantics: single-use, payload-bound, strict (F-02, F-04)
- **Files:** `platform/guardrails/approval_gate.py`, `platform/guardrails/api.py`, `tools/log_claim.py`, `tools/issue_payment.py`, prompt (only if `issue_payment`'s arguments change and it stays offered, as a new version per AGENTS.md), and the tests for all of these
- **Reason:** One approval must authorise exactly one execution of exactly what the human saw, before W3 makes execution real.
- **Acceptance criteria:**
  - After `approve`, the first `check` for that key returns `approved=True` and moves the request to a terminal consumed state atomically. The second returns `approved=False`. Tested.
  - The `log_claim` context contains the rules-derived `eligible` / `compensation_eur` / `reasons` and a facts digest. Changed facts produce a new pending request. Tested.
  - `issue_payment` gets its amount from `rules.evaluate()` rather than from the model. Tested with a model-supplied amount that would disagree.
  - `check_approval` requires a non-empty context.
  - `ApprovalRequest` is frozen; state transitions replace it under the lock, and `check` reads the status under the lock.
  - `list_pending` / `/approvals` still show everything the human needs to decide, with no raw `claim_text`.
- **Depends on:** T-2, T-3

### T-5: Memory stays out of the system prompt's trust level (F-06)
- **Files:** `agent/graph.py` (`dispatch_tools`, `_augmented_system`), `agent/memory/short_term.py`, `application/triage_use_case.py` (what gets saved to long-term), and the memory tests
- **Reason:** W3's RAG and injection work must not start from a design where retrieved or user-influenced text becomes system instructions.
- **Acceptance criteria:**
  - Raw `ToolResult.content` is never copied into the system prompt.
  - Long-term memory stores only structured, rules-derived fields and no `explanation` text.
  - The system prompt is identical on every turn of a run: a test asserts the fake provider saw the same `system` on every call.
  - The existing cross-run memory tests are adapted, not deleted.
- **Depends on:** nothing

### T-6: One graph behind both triage endpoints, or remove streaming (F-07)
- **Files:** `agent/graph.py`, `application/triage_use_case.py`, `api/routes.py`, `platform/ai/streaming.py` (only if a platform-level event is needed; feature-level frames stay in `features/`), the route and use-case tests, and `docs/decisions/0007-…` if the endpoint is removed
- **Reason:** No unverified path should reach W3's guardrails and end-to-end tests.
- **Acceptance criteria:**
  - Either (i) `stream_triage` drives the compiled graph, the old manual loop and its `RuntimeError` are deleted, and the SSE stream ends with one `final` frame carrying the same fields as `TriageResponse`, plus an `error` frame on exceptions; or (ii) the endpoint and `stream_triage` are removed and ADR-0007 is updated.
  - The existing streaming tests are ported (option i) or removed (option ii).
  - Under (i), a test shows a verification mismatch on the stream path ends in repair or escalation, not a raw verdict.
- **Depends on:** T-1 (so both paths share the corrected escalation output)

---

## 5. Optional Improvements

Each one has a natural home in the plan. None of them blocks W3.

| # | Improvement | When | Findings |
|---|---|---|---|
| O-1 | Build the provider, stores and gate once in `create_app()` and inject them through `Depends`; tests use `dependency_overrides` | First step of W3 "Set up Postgres" | F-08 |
| O-2 | Decide the RAG entry point (`search_kb`) and delete the unused `classify`/`retrieve`/`decide` stubs | W3 RAG kickoff | F-10 |
| O-3 | Prompt v5 covering the real tool catalogue, gated on the W3 eval set | W3 RAG and eval tasks | F-09 |
| O-4 | `make test-integration` and a minimal CI job running `make test` | When W3's Docker integration tests land | F-11 |
| O-5 | `ANTHROPIC_MAX_TOKENS` config with a 4096 default | Any time | F-12 |
| O-6 | Bind the compose API port to localhost, and a shared-secret header on `/approvals/*` | W3 Docker Compose task | F-13 |
| O-7 | Hygiene batch: `FallbackProvider` docstring, `openai` dependency group, `claim_text` `max_length`, `McpToolClient` enter leak, empty test placeholders, rewording `1c0ea0b` | Any time; about 30 minutes | F-11, F-14 |

---

## 6. Proposed Pre-W3 Execution Plan

- [x] **T-1:** Escalated runs return a fixed human-review `answer` and never the model's rejected text; assert `answer` in the escalation tests
- [x] **T-5:** Stop copying tool results into the system prompt; long-term memory stores rules-derived fields only; the system prompt stays constant within a run
- [x] **T-2:** Amend or supersede ADR-0008: execution model, single-use and payload-bound approvals, server-issued `claim_id`, shared store in W3, which tools the agent is offered, the `log_claim` policy intent
- [x] **T-3:** Server-issued `claim_id` bound into the per-run tool registry, returned in the API response
- [x] **T-4:** Single-use, payload-bound, strict approvals; `issue_payment` amount derived from the rules engine; frozen `ApprovalRequest`
- [x] **T-6:** `/triage/stream` runs on the graph with a `final` frame and an `error` frame (or is removed and ADR-0007 updated)
- [x] **O-7 (recommended, about 30 minutes):** hygiene batch (done in `7ac4d85`; rewording commit `1c0ea0b` still pending — it needs a force-push)
- [x] `make test` green; add a "Pre-W3 hardening" entry to `docs/ombuds_build_task_summaries.md`; update README step 6 if T-2 changes the described flow

Estimated effort: about 2 days.

- T-1, T-2 and T-5: under 2 hours each.
- T-3 and T-4 together: about half a day.
- T-6: about half a day on the graph, or under an hour if the endpoint is removed.

---

## 7. Final Recommendation

**Ready for W3 after the required refactoring.**

The foundation is in good shape, and W3 can build on this layout as it is:

- the layering holds;
- W1's hardening landed properly;
- the LangGraph rebuild is clean and bounded;
- escalation is modelled as an outcome rather than a crash;
- MCP follows ADR-0003 exactly;
- lint, mypy strict and 135 tests pass.

**No restructuring is needed.**

W2's gaps are concentrated in one area: **the governance path's semantics**. Each gap either breaks the project's core claim today or is about to be persisted by W3:

- **F-01, F-04 and F-07** are three places where a model-authored eligibility or amount still reaches a caller or an approver: the escalation `answer`, `issue_payment`'s amount, and the unverified stream endpoint. The invariant is enforced on the main path but not on these.
- **F-02, F-03 and F-05** concern approvals: an approval is reusable, not bound to its payload, and keyed on an id the model invents, and nothing leads from "approved" to "executed". All of this is harmless while execution raises "not implemented". W3 is exactly where execution and the approval schema get built, so the semantics have to be fixed first. Otherwise the Postgres tables will encode them.
- **F-06** has to be settled before W3's RAG and injection work, which would otherwise inherit a design where retrieved or user-influenced text is promoted into the system prompt.

Everything else (DI at the composition root, the RAG entry point, prompt v5, CI, `max_tokens`, auth) is real, but belongs *inside* the W3 tasks that touch that code.
