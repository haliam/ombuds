# ADR-0009: The approval request is the pending action, executed exactly once after a human approves it

**Status:** accepted (supersedes ADR-0008)
**Date:** 2026-09-28

## Context
ADR-0008 made the human-approval gate a deny-and-dedupe check: a state-changing tool call creates a `PENDING` request, and "the *next* call with the same action/context sees the resolution". The W2 review (`docs/reviews/w2_review_pre_w3_plan.md`, F-02 to F-05) found that this model has no path from approval to execution:

- Nothing makes that "next call". The run that hit the gate has ended, and a new run would have to reproduce the same model-invented `claim_id` and context.
- An approval, once granted, stayed approved for every later check, so one approval would have allowed unlimited executions.
- The approval context didn't hold what the human was approving (for `log_claim`, only a bare `claim_id`).
- The in-memory gate is per process, and ADR-0008's own revisit trigger has already fired: with `use_mcp=True`, the gate lives in the MCP subprocess, where `/approvals` can't see it.

W3 designs the Postgres tables for claims and approvals, so the execution model has to be fixed first. There were two real options:

- (a) the approval request stores the action and a separate step executes it;
- (b) LangGraph `interrupt()` plus a checkpointer, resumed after the human decides.

## Decision
A state-changing tool call never executes inline. It submits a `PENDING` approval request whose payload is the exact, rules-derived action (never a model-authored eligibility or amount). A human approves or denies that request. An approved request is executed **exactly once**, by an executor registered for its action, through a single-use `APPROVED → EXECUTED` transition. The LLM is not re-invoked to retry the call.

Along with this:

- **Approvals are bound to their payload.** The dedup key is `(action, payload)`, so changed facts create a new request. The payload holds everything the approver needs to decide, and never the raw `claim_text`.
- **`claim_id` is issued by the server.** `run_triage` assigns or accepts it. The model can't choose it: any `claim_id` argument the model passes is replaced with the run's own. An external MCP client supplies `claim_id` itself, and from W3 it is validated against the `claims` table.
- **The triage agent's tool set is `search_kb`, `check_eligibility` and `log_claim`.** `issue_payment` is not offered to the agent. A payment is a separate downstream action on an approved, logged claim, whose amount comes from the rules engine or the logged claim record. It stays exposed over MCP for operators.
- **The intended W4 end state:** `log_claim` (a rules-derived decision record) auto-executes when the W4 OPA policy allows it. Any money-moving action (`issue_payment`) always requires a human. Until the policy engine exists, `log_claim` also requires a human.
- **The store must be shared across processes.** In W3 it moves to Postgres, and the `APPROVED → EXECUTED` transition happens in the same transaction as the executor's write. It stays in memory, per process, until then.

## Consequences
- **Easier:** execution is deterministic and auditable. It is the same code path whether the request came from the in-process agent or an MCP client, and it can't be replayed or duplicated.
- **Easier:** idempotency is structural. A retried tool call dedupes onto the existing request, which may already be `EXECUTED`, and a request executes at most once.
- **Easier:** the approver sees rules-engine output, not model output.
- **Harder:** the agent can't tell the passenger the final outcome in the same run. It can only say the claim was submitted for review. Any notification after execution belongs to the executor side (W3/W4).
- **Harder:** executors are new wiring. The composition root registers one per action, and there are none before W3's persistence exists.
- **Revisit if:** a use case needs the *same agent run* to continue after a human decision, such as a multi-step negotiation with the passenger. That would bring back option (b).

## Alternatives considered
- **(b) LangGraph `interrupt()` plus a checkpointer.** Idiomatic for LangGraph, but the interrupt has to happen in a graph node rather than in the tool, so it doesn't cover external MCP clients, and approvals would be tied to graph checkpoints rather than to a domain record. Rejected for now, and kept as the revisit path above.
- **ADR-0008's retry-the-tool-call model.** It had no path to execution, and approvals weren't single-use (see Context).

## Lifecycle of an approval request

Diagram: [Approval Request Lifecycle v1.0](../diagrams/approval-lifecycle.md)

## Addendum (2026-10-15): executors and the transaction model

W3 left the approval path unfinished (W3 review F-01): the Postgres store existed but nothing executed an approved request. The pre-W4 refactor (P-1, P-2) completes it.

- **Execution happens on approve.** `ExecutingApprovalStore` (`platform/guardrails/executing_store.py`) decorates the runtime `ApprovalStore`. `approve()` wins the `PENDING → APPROVED` compare-and-set, runs the executor registered for the request's action, then wins `APPROVED → EXECUTED`. Only one concurrent approve can win the first transition, so only one execution is triggered; every later approve or `claim_for_execution` raises `ApprovalStateError` and writes nothing. Every `GuardedAction` must have an executor, checked at construction. The claims-triage executors live in `features/claims_triage/application/executors.py`; `application/runtime.py` is the one place that wires store, executors and tools, shared by `api_app.py` and the MCP server.
- **Transaction model: idempotent write, then claim.** The executor's write is not in the same database transaction as the status transition. Instead each executor write is idempotent (`INSERT ... ON CONFLICT (claim_id) DO NOTHING`) and runs *before* `APPROVED → EXECUTED`. A crash or executor failure in between leaves the request `APPROVED` with the effect recorded at most once, and `execute_approved()` re-runs it safely. This was chosen over a single transaction because it keeps the store protocol free of connection handling and works for any future executor, including one whose effect is outside Postgres. The cost is that a failed execution surfaces as an error from `approve` (HTTP 500) and needs `execute_approved` to finish; nothing calls that automatically yet.
- **`log_claim`** executes by inserting the `claims` row (the rules-derived decision and the facts it came from).
- **`issue_payment`** requires a logged claim whose recorded `compensation_eur` equals the requested amount. This is checked when the payment is requested (a `ToolExecutionError`, so no approval request exists for an unlogged or mismatched payment) and again when it executes. Its executor inserts a row in `payments` (migration `0002`, one per claim).
- **There is no real payment rail.** A "payment" is a simulated payout record in `payments`; nothing moves money.
- **The store is shared across processes.** The API and the MCP server subprocess both build the Postgres-backed runtime, so there is no longer a per-process gate or a single-replica constraint from the gate.
