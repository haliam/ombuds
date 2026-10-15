"""Run an approved request's executor exactly once (ADR-0009 addendum).

`ExecutingApprovalStore` decorates any `ApprovalStore`: approving a request runs the executor registered for
its action, then wins the single-use `APPROVED -> EXECUTED` transition. The executor's write is idempotent
and runs *before* that transition, so a crash between the two leaves the request `APPROVED` with the effect
recorded at most once; `execute_approved` re-runs it safely. Only one `approve` can win the
`PENDING -> APPROVED` compare-and-set, so concurrent approvals trigger one execution, and a second approval
or claim attempt raises `ApprovalStateError` and writes nothing.
"""

from collections.abc import Callable, Mapping

from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import (
    ApprovalRequest,
    ApprovalStateError,
    ApprovalStatus,
    ApprovalStore,
    GuardedAction,
)

Executor = Callable[[ApprovalRequest], None]
"""Performs one approved action's effect. Must be idempotent on the request: it may be re-run after a crash."""


class ExecutingApprovalStore:
    """An `ApprovalStore` whose `approve` also executes the approved action."""

    def __init__(self, inner: ApprovalStore, executors: Mapping[GuardedAction, Executor]) -> None:
        missing = set(GuardedAction) - set(executors)
        if missing:
            raise ValueError(f"no executor registered for: {', '.join(sorted(missing))}")
        self._inner = inner
        self._executors = executors

    def submit(self, action: GuardedAction, payload: Mapping[str, JsonValue]) -> ApprovalRequest:
        return self._inner.submit(action, payload)

    def list_pending(self) -> tuple[ApprovalRequest, ...]:
        return self._inner.list_pending()

    def get(self, request_id: str) -> ApprovalRequest:
        return self._inner.get(request_id)

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._inner.deny(request_id, approver, note)

    def claim_for_execution(self, request_id: str) -> ApprovalRequest:
        return self._inner.claim_for_execution(request_id)

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        """Approve a `PENDING` request and execute it; returns the request in its final (`EXECUTED`) state."""
        self._inner.approve(request_id, approver, note)
        return self.execute_approved(request_id)

    def execute_approved(self, request_id: str) -> ApprovalRequest:
        """Execute an `APPROVED` request: run its executor, then mark it `EXECUTED`.

        Also the recovery path for a request left `APPROVED` by a crash or an executor failure.
        """
        request = self._inner.get(request_id)
        if request.status is not ApprovalStatus.APPROVED:
            raise ApprovalStateError(f"approval request {request_id} is {request.status}, not approved; cannot execute")
        self._executors[request.action](request)
        return self._inner.claim_for_execution(request_id)
