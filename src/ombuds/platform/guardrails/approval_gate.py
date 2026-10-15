"""Human-approval gate: a state-changing action is submitted as a pending request, never executed inline.

Every state-changing tool (`log_claim`, `issue_payment`) submits the exact payload it wants executed to the
`ApprovalStore` its composition root gave it. A human then approves or denies that request (over HTTP,
`platform/guardrails/api.py`), and an approved request is executed at most once: the executor that runs it
must first win
`claim_for_execution`, an atomic `APPROVED -> EXECUTED` transition. See ADR-0009, which supersedes ADR-0008.

Requests dedupe on `(action, payload)`: re-submitting the same action for the same payload returns the
existing request in whatever state it's in, so a retried tool call can't create a duplicate, and a payload
that changes (different facts, a different amount) is a new request the human has to approve separately.
"""

import json
import uuid
from collections.abc import Mapping
from enum import StrEnum
from threading import Lock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, JsonValue

from ombuds.platform.guardrails.pii_filter import redact


class GuardedAction(StrEnum):
    """State-changing actions that must pass through the approval gate."""

    LOG_CLAIM = "log_claim"
    ISSUE_PAYMENT = "issue_payment"


class ApprovalStatus(StrEnum):
    """Lifecycle of one approval request: `PENDING -> APPROVED -> EXECUTED`, or `PENDING -> DENIED`."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"


class ApprovalRequest(BaseModel):
    """One request for a human to approve or deny a guarded action with an exact payload."""

    model_config = ConfigDict(frozen=True)

    id: str
    action: GuardedAction
    payload: dict[str, JsonValue]
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver: str | None = None
    note: str | None = None


class ApprovalNotFoundError(Exception):
    """Raised when given a request id that doesn't exist."""


class ApprovalStateError(Exception):
    """Raised for a transition the request's current status doesn't allow (e.g. approving it twice)."""


def dedup_key(action: GuardedAction, payload: Mapping[str, JsonValue]) -> tuple[str, str]:
    return (action, json.dumps(payload, sort_keys=True, separators=(",", ":")))


class ApprovalStore(Protocol):
    """What the gate needs from a store of approval requests; `ApprovalGate` and the Postgres store both fit."""

    def submit(self, action: GuardedAction, payload: Mapping[str, JsonValue]) -> ApprovalRequest: ...

    def list_pending(self) -> tuple[ApprovalRequest, ...]: ...

    def get(self, request_id: str) -> ApprovalRequest: ...

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest: ...

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest: ...

    def claim_for_execution(self, request_id: str) -> ApprovalRequest: ...


def _redacted(note: str | None) -> str | None:
    """An approver's free-text note, with PII removed: it's stored and listed by `/approvals`."""
    return None if note is None else redact(note).text


class ApprovalGate:
    """In-memory, lock-guarded store of approval requests.

    The in-memory fake for tests: per-instance, so nothing is shared through a global. The runtime store is
    `PostgresApprovalStore`, which the API and the MCP server subprocess both open (ADR-0009).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[str, ApprovalRequest] = {}
        self._by_key: dict[tuple[str, str], str] = {}

    def submit(self, action: GuardedAction, payload: Mapping[str, JsonValue]) -> ApprovalRequest:
        """Create a `PENDING` request for `action`/`payload`, or return the existing one in its current state."""
        if not payload:
            raise ValueError("an approval request needs a non-empty payload describing exactly what is approved")
        key = dedup_key(action, payload)
        with self._lock:
            request_id = self._by_key.get(key)
            if request_id is None:
                request_id = str(uuid.uuid4())
                self._requests[request_id] = ApprovalRequest(id=request_id, action=action, payload=dict(payload))
                self._by_key[key] = request_id
            return self._requests[request_id]

    def list_pending(self) -> tuple[ApprovalRequest, ...]:
        with self._lock:
            return tuple(r for r in self._requests.values() if r.status is ApprovalStatus.PENDING)

    def get(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            return self._get(request_id)

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        """Approve a `PENDING` request. Approving never executes anything by itself — see `claim_for_execution`."""
        return self._transition(
            request_id, ApprovalStatus.PENDING, ApprovalStatus.APPROVED, approver=approver, note=_redacted(note)
        )

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        """Deny a `PENDING` request. Terminal: a denied payload can't be re-approved, only re-submitted changed."""
        return self._transition(
            request_id, ApprovalStatus.PENDING, ApprovalStatus.DENIED, approver=approver, note=_redacted(note)
        )

    def claim_for_execution(self, request_id: str) -> ApprovalRequest:
        """Atomically move an `APPROVED` request to `EXECUTED` and return it; raise for any other status.

        The single-use primitive: exactly one caller wins the right to execute a given approval, so one
        human approval can never authorise two executions.
        """
        return self._transition(request_id, ApprovalStatus.APPROVED, ApprovalStatus.EXECUTED)

    def _get(self, request_id: str) -> ApprovalRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise ApprovalNotFoundError(f"no approval request with id {request_id}")
        return request

    def _transition(
        self,
        request_id: str,
        from_status: ApprovalStatus,
        to_status: ApprovalStatus,
        **updates: str | None,
    ) -> ApprovalRequest:
        with self._lock:
            request = self._get(request_id)
            if request.status is not from_status:
                raise ApprovalStateError(
                    f"approval request {request_id} is {request.status}, not {from_status}; cannot mark it {to_status}"
                )
            updated = request.model_copy(update={"status": to_status, **updates})
            self._requests[request_id] = updated
            return updated
