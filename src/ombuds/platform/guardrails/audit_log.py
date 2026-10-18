"""The audit trail's vocabulary: what an event is, and the sink every governance seam writes to (ADR-0016).

`AuditEvent` carries identifiers, outcomes and reason codes, never raw claim data: tool arguments reach it
already redacted (the dispatcher sits inside `GuardedDispatcher`, ADR-0013), and approval payloads are not
copied at all, only the ids that point at them.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, JsonValue


class AuditKind(StrEnum):
    """What happened. Mirrors the `CHECK` constraint on `audit_log.kind`."""

    TOOL_CALL = "tool_call"
    POLICY_DECISION = "policy_decision"
    APPROVAL_SUBMITTED = "approval_submitted"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_EXECUTED = "approval_executed"


class AuditEvent(BaseModel):
    """One thing that happened: a tool call, a policy verdict or an approval transition."""

    model_config = ConfigDict(frozen=True)

    kind: AuditKind
    subject: str
    """The tool name or guarded action the event is about."""
    outcome: str
    """`ok`/`error` for a tool call, `allow`/`deny` for a policy verdict, the new status for an approval."""
    claim_id: str | None = None
    approval_request_id: str | None = None
    detail: dict[str, JsonValue] = {}
    trace_id: str | None = None


class AuditLog(Protocol):
    """Where events go; `PostgresAuditLog` is the runtime sink and tests use an in-memory fake."""

    def record(self, event: AuditEvent) -> None: ...
