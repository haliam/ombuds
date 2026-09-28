"""Human-approval gate.

Every state-changing tool (`log_claim`, `issue_payment`) must call `check_approval` before executing.
A tool being registered and callable is not the same as being permitted to run: the first `check_approval`
call for a given action/context creates a `PENDING` request and denies the call. A human then resolves it
via `approve`/`deny` (exposed over HTTP by `platform/guardrails/api.py`), and the *next* call with the same
action/context sees that resolution. See ADR-0008.
"""

import uuid
from collections.abc import Mapping
from enum import StrEnum
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field


class GuardedAction(StrEnum):
    """State-changing actions that must pass through the approval gate."""

    LOG_CLAIM = "log_claim"
    ISSUE_PAYMENT = "issue_payment"


class ApprovalStatus(StrEnum):
    """Lifecycle of one approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ApprovalRequest(BaseModel):
    """One request for a human to approve or deny a guarded action, keyed by `action` + `context`."""

    model_config = ConfigDict(frozen=False)

    id: str
    action: GuardedAction
    context: Mapping[str, str | int]
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver: str | None = None
    note: str | None = None


class ApprovalDecision(BaseModel):
    """Outcome of an approval check."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    reason: str
    request_id: str = Field(description="The `ApprovalRequest.id` this decision resolves, for follow-up.")


class ApprovalNotFoundError(Exception):
    """Raised by `approve`/`deny` when given a request id that doesn't exist."""


def _context_key(action: GuardedAction, context: Mapping[str, str | int]) -> tuple[object, ...]:
    return (action, tuple(sorted(context.items())))


class ApprovalGate:
    """In-memory store of approval requests, keyed by `(action, context)` so repeated calls for the same
    action dedupe onto the same request instead of piling up duplicates."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[str, ApprovalRequest] = {}
        self._by_key: dict[tuple[object, ...], str] = {}

    def check(self, action: GuardedAction, context: Mapping[str, str | int]) -> ApprovalDecision:
        """Look up (or create) the request for `action`/`context` and report its current status.

        A brand-new request starts `PENDING` and is denied — the same as an unresolved one. Only an
        explicitly `approve`d request is approved.
        """
        key = _context_key(action, context)
        with self._lock:
            request_id = self._by_key.get(key)
            if request_id is None:
                request_id = str(uuid.uuid4())
                self._requests[request_id] = ApprovalRequest(id=request_id, action=action, context=context)
                self._by_key[key] = request_id
            request = self._requests[request_id]

        if request.status is ApprovalStatus.APPROVED:
            return ApprovalDecision(approved=True, reason=f"approved by {request.approver}", request_id=request.id)
        if request.status is ApprovalStatus.DENIED:
            return ApprovalDecision(
                approved=False,
                reason=f"denied by {request.approver}" + (f": {request.note}" if request.note else ""),
                request_id=request.id,
            )
        return ApprovalDecision(
            approved=False,
            reason=f"awaiting human approval (request {request.id})",
            request_id=request.id,
        )

    def list_pending(self) -> tuple[ApprovalRequest, ...]:
        with self._lock:
            return tuple(r for r in self._requests.values() if r.status is ApprovalStatus.PENDING)

    def get(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            request = self._requests.get(request_id)
        if request is None:
            raise ApprovalNotFoundError(f"no approval request with id {request_id}")
        return request

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._resolve(request_id, ApprovalStatus.APPROVED, approver, note)

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._resolve(request_id, ApprovalStatus.DENIED, approver, note)

    def _resolve(self, request_id: str, status: ApprovalStatus, approver: str, note: str | None) -> ApprovalRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise ApprovalNotFoundError(f"no approval request with id {request_id}")
            request.status = status
            request.approver = approver
            request.note = note
            return request


_GATE = ApprovalGate()


def check_approval(action: GuardedAction, context: Mapping[str, str | int] | None = None) -> ApprovalDecision:
    """Check (creating if needed) the approval request for `action`/`context` against the module-level gate."""
    return _GATE.check(action, context or {})


def list_pending_approvals() -> tuple[ApprovalRequest, ...]:
    return _GATE.list_pending()


def get_approval_request(request_id: str) -> ApprovalRequest:
    return _GATE.get(request_id)


def approve_request(request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
    return _GATE.approve(request_id, approver, note)


def deny_request(request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
    return _GATE.deny(request_id, approver, note)
