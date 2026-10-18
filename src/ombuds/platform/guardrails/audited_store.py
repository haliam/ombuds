"""An `ApprovalStore` that records each approval transition in the audit log (ADR-0016).

Wraps the durable store *inside* `ExecutingApprovalStore`, so it sees the real transitions: `approve` and
`claim_for_execution` are separate events, and the recovery path (`execute_approved`) is audited too. Only
the request id, action, claim id and approver are recorded; the payload and the approver's note are not
copied (the note is free text), they stay on the request row.
"""

from collections.abc import Mapping

from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import ApprovalRequest, ApprovalStore, GuardedAction
from ombuds.platform.guardrails.audit_log import AuditEvent, AuditKind, AuditLog


class AuditedApprovalStore:
    """Decorates an `ApprovalStore`; a transition is recorded only after the inner store accepts it."""

    def __init__(self, inner: ApprovalStore, audit: AuditLog) -> None:
        self._inner = inner
        self._audit = audit

    def submit(self, action: GuardedAction, payload: Mapping[str, JsonValue]) -> ApprovalRequest:
        return self._record(AuditKind.APPROVAL_SUBMITTED, self._inner.submit(action, payload))

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._record(AuditKind.APPROVAL_APPROVED, self._inner.approve(request_id, approver, note))

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._record(AuditKind.APPROVAL_DENIED, self._inner.deny(request_id, approver, note))

    def claim_for_execution(self, request_id: str) -> ApprovalRequest:
        return self._record(AuditKind.APPROVAL_EXECUTED, self._inner.claim_for_execution(request_id))

    def list_pending(self) -> tuple[ApprovalRequest, ...]:
        return self._inner.list_pending()

    def get(self, request_id: str) -> ApprovalRequest:
        return self._inner.get(request_id)

    def _record(self, kind: AuditKind, request: ApprovalRequest) -> ApprovalRequest:
        claim_id = request.payload.get("claim_id")
        detail: dict[str, JsonValue] = {} if request.approver is None else {"approver": request.approver}
        self._audit.record(
            AuditEvent(
                kind=kind,
                subject=request.action,
                outcome=request.status,
                claim_id=claim_id if isinstance(claim_id, str) else None,
                approval_request_id=request.id,
                detail=detail,
            )
        )
        return request
