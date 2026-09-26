"""Deny-all approval gate.

Every state-changing tool (`log_claim`, `issue_payment`) must call
`check_approval` before executing. This is a stub: it denies every action
unconditionally. The real human-approval workflow lands in W2 (ADR-0004).
Until then, a tool being registered and callable must never be mistaken for
a tool being permitted to run.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class GuardedAction(StrEnum):
    """State-changing actions that must pass through the approval gate."""

    LOG_CLAIM = "log_claim"
    ISSUE_PAYMENT = "issue_payment"


class ApprovalDecision(BaseModel):
    """Outcome of an approval check."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    reason: str


def check_approval(action: GuardedAction) -> ApprovalDecision:
    """Deny the given action.

    Stub for the real approval gate; denies every `GuardedAction`
    unconditionally, regardless of caller or arguments.
    """
    return ApprovalDecision(approved=False, reason=f"approval_gate stub denies all actions (denied: {action})")
