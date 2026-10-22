"""An executable in-memory store for unit tests that need `ExecutableApprovalStore` over an `ApprovalGate`."""

from collections.abc import Callable

from ombuds.platform.guardrails.approval_gate import ApprovalGate, ApprovalRequest, GuardedAction
from ombuds.platform.guardrails.executing_store import ExecutingApprovalStore


def _do_nothing(request: ApprovalRequest) -> None:
    return None


def executing(gate: ApprovalGate, executor: Callable[[ApprovalRequest], None] = _do_nothing) -> ExecutingApprovalStore:
    """`gate` wrapped so approving it runs `executor` (a no-op by default) for every action."""
    return ExecutingApprovalStore(gate, {action: executor for action in GuardedAction})
