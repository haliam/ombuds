"""An `ApprovalStore` that asks the policy engine before it accepts a submission (ADR-0015).

A denied action never becomes an approval request, so no human can approve it from the queue. Policy runs on
`submit` only: every state-changing tool, in-process or over MCP, reaches the store through it. Everything
else delegates unchanged.
"""

from collections.abc import Mapping

from pydantic import JsonValue

from ombuds.domain.errors import PolicyDeniedError
from ombuds.platform.guardrails.approval_gate import ApprovalRequest, ApprovalStore, GuardedAction
from ombuds.platform.guardrails.policy_engine import PolicyEngine


class PolicyCheckedApprovalStore:
    """Decorates an `ApprovalStore`; `submit` raises `PolicyDeniedError` when the policy denies the action."""

    def __init__(self, inner: ApprovalStore, engine: PolicyEngine, limits: Mapping[str, JsonValue]) -> None:
        self._inner = inner
        self._engine = engine
        self._limits = dict(limits)

    def submit(self, action: GuardedAction, payload: Mapping[str, JsonValue]) -> ApprovalRequest:
        decision = self._engine.evaluate({"action": action, "payload": dict(payload), "limits": self._limits})
        if not decision.allow:
            raise PolicyDeniedError(action, decision.reasons)
        return self._inner.submit(action, payload)

    def list_pending(self) -> tuple[ApprovalRequest, ...]:
        return self._inner.list_pending()

    def get(self, request_id: str) -> ApprovalRequest:
        return self._inner.get(request_id)

    def approve(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._inner.approve(request_id, approver, note)

    def deny(self, request_id: str, approver: str, note: str | None = None) -> ApprovalRequest:
        return self._inner.deny(request_id, approver, note)

    def claim_for_execution(self, request_id: str) -> ApprovalRequest:
        return self._inner.claim_for_execution(request_id)
