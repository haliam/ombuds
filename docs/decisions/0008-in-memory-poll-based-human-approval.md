# ADR-0008: In-memory, poll-based human-approval gate over the deny-all stub

**Status:** superseded by ADR-0009
**Date:** 2026-09-28

## Context
`platform/guardrails/approval_gate.py` shipped in W1 as a deny-all stub (ADR-0004) so `log_claim`/`issue_payment` could be wired and tested before a real approval workflow existed. Replacing it needed a decision on two independent axes: where approval requests are persisted, and what `check_approval` does the first time it sees a given action. The triage HTTP endpoints are plain request/response (ADR-0007 chose SSE, one-directional) — there's no mid-request channel for a human to answer synchronously, so any real workflow is necessarily asynchronous: create a request now, resolve it separately, see the resolution on a later call.

## Decision
`check_approval(action, context)` dedupes on `(action, context)` and, the first time it sees a given pair, creates a `PENDING` `ApprovalRequest` in an in-memory `ApprovalGate` and denies the call. A human resolves it via `platform/guardrails/api.py` (`GET /approvals`, `POST /approvals/{id}/approve|deny`), and the *next* call with the same action/context sees that resolution — there is no push back into the triage loop that made the original call.

## Consequences
- `log_claim`/`issue_payment` need no new argument or return type: they already re-check `check_approval` on every call, so approval "arrives" the next time the same claim is retried through the loop.
- State resets on process restart. Acceptable for the current single-process demo; would need to move to a real store before this survives redeploys or multiple workers.
- Dedup key is `(action, context)`, not a caller-supplied idempotency token — two distinct claims with identical context (unlikely, since `claim_id` is always in it) would collide onto one request. Not a concern while `claim_id` is always part of the context.
- No caller identity/authz on `/approvals/*` yet — `approver` is a free-text field the caller supplies. Fine for a capstone demo; a real deployment would need to authenticate who's approving.
- Revisit if: the app needs multiple processes/workers (state must move to Postgres, mirroring `audit_repository.py`), or the triage loop needs to *wait* for a decision mid-run rather than being re-invoked after one (would need the WebSocket path ADR-0007 already flagged as a future revisit, not SSE).

## Alternatives considered
- **Postgres-backed approval requests** — the more realistic long-term shape (survives restarts, supports multiple workers), but a bigger surface (migration, repository, tests) for a decision that's easy to swap in later since `ApprovalGate`'s interface (`check`/`approve`/`deny`/`list_pending`) doesn't change if the backing store does.
- **Require the caller to pre-create the `ApprovalRequest` explicitly** — more explicit, but pushes request-creation into `log_claim`/`issue_payment` themselves, duplicating what `check_approval` can just do on first sight of a new action/context.
