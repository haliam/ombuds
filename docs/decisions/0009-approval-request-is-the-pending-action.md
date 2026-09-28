# ADR-0009: The approval request is the pending action, executed exactly once after a human approves it

**Status:** accepted (supersedes ADR-0008)
**Date:** 2026-09-28

## Context
ADR-0008 made the human-approval gate a deny-and-dedupe check: a state-changing tool call creates a `PENDING` request, and "the *next* call with the same action/context sees the resolution". The W2 review (`docs/w2_review_pre_w3_plan.md`, F-02 to F-05) found that this model has no path from approval to execution:

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
