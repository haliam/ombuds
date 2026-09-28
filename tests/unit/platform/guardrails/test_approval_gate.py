import pytest

from ombuds.platform.guardrails.approval_gate import (
    ApprovalGate,
    ApprovalNotFoundError,
    GuardedAction,
)


@pytest.fixture
def gate() -> ApprovalGate:
    return ApprovalGate()


@pytest.mark.parametrize("action", list(GuardedAction))
def test_first_check_creates_a_pending_request_and_denies(gate: ApprovalGate, action: GuardedAction) -> None:
    decision = gate.check(action, {"claim_id": "claim-1"})

    assert decision.approved is False
    assert "awaiting human approval" in decision.reason
    assert decision.request_id


def test_repeat_check_with_same_context_dedupes_onto_the_same_request(gate: ApprovalGate) -> None:
    first = gate.check(GuardedAction.LOG_CLAIM, {"claim_id": "claim-1"})
    second = gate.check(GuardedAction.LOG_CLAIM, {"claim_id": "claim-1"})

    assert first.request_id == second.request_id
    assert len(gate.list_pending()) == 1


def test_different_context_creates_a_separate_request(gate: ApprovalGate) -> None:
    first = gate.check(GuardedAction.LOG_CLAIM, {"claim_id": "claim-1"})
    second = gate.check(GuardedAction.LOG_CLAIM, {"claim_id": "claim-2"})

    assert first.request_id != second.request_id
    assert len(gate.list_pending()) == 2


def test_approved_request_is_approved_on_next_check(gate: ApprovalGate) -> None:
    pending = gate.check(GuardedAction.ISSUE_PAYMENT, {"claim_id": "claim-1"})
    gate.approve(pending.request_id, approver="ops-lead")

    decision = gate.check(GuardedAction.ISSUE_PAYMENT, {"claim_id": "claim-1"})

    assert decision.approved is True
    assert "ops-lead" in decision.reason
    assert decision.request_id == pending.request_id
    assert gate.list_pending() == ()


def test_denied_request_stays_denied_and_carries_the_note(gate: ApprovalGate) -> None:
    pending = gate.check(GuardedAction.ISSUE_PAYMENT, {"claim_id": "claim-1"})
    gate.deny(pending.request_id, approver="ops-lead", note="insufficient evidence")

    decision = gate.check(GuardedAction.ISSUE_PAYMENT, {"claim_id": "claim-1"})

    assert decision.approved is False
    assert "ops-lead" in decision.reason
    assert "insufficient evidence" in decision.reason


def test_approving_an_unknown_request_id_raises(gate: ApprovalGate) -> None:
    with pytest.raises(ApprovalNotFoundError):
        gate.approve("no-such-id", approver="ops-lead")


def test_denying_an_unknown_request_id_raises(gate: ApprovalGate) -> None:
    with pytest.raises(ApprovalNotFoundError):
        gate.deny("no-such-id", approver="ops-lead")
