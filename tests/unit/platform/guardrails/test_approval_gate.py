import pytest
from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import (
    ApprovalGate,
    ApprovalNotFoundError,
    ApprovalStateError,
    ApprovalStatus,
    GuardedAction,
)

_PAYLOAD: dict[str, JsonValue] = {"claim_id": "claim-1", "eligible": True, "compensation_eur": 250}


@pytest.fixture
def gate() -> ApprovalGate:
    return ApprovalGate()


@pytest.mark.parametrize("action", list(GuardedAction))
def test_submit_creates_a_pending_request_holding_the_exact_payload(gate: ApprovalGate, action: GuardedAction) -> None:
    request = gate.submit(action, _PAYLOAD)

    assert request.status is ApprovalStatus.PENDING
    assert request.action is action
    assert request.payload == _PAYLOAD
    assert gate.list_pending() == (request,)


def test_resubmitting_the_same_payload_dedupes_onto_the_same_request(gate: ApprovalGate) -> None:
    first = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    second = gate.submit(GuardedAction.LOG_CLAIM, dict(reversed(list(_PAYLOAD.items()))))

    assert first.id == second.id
    assert len(gate.list_pending()) == 1


def test_a_changed_payload_is_a_separate_request(gate: ApprovalGate) -> None:
    first = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    second = gate.submit(GuardedAction.LOG_CLAIM, {**_PAYLOAD, "compensation_eur": 400})

    assert first.id != second.id
    assert len(gate.list_pending()) == 2


def test_an_empty_payload_is_rejected(gate: ApprovalGate) -> None:
    with pytest.raises(ValueError, match="non-empty payload"):
        gate.submit(GuardedAction.LOG_CLAIM, {})


def test_approving_does_not_by_itself_approve_other_payloads_for_the_same_claim(gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    gate.approve(request.id, approver="ops-lead")

    changed = gate.submit(GuardedAction.LOG_CLAIM, {**_PAYLOAD, "compensation_eur": 600})

    assert changed.status is ApprovalStatus.PENDING


def test_resubmitting_an_approved_payload_returns_it_in_its_current_state(gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    gate.approve(request.id, approver="ops-lead", note="verified")

    again = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    assert again.id == request.id
    assert again.status is ApprovalStatus.APPROVED
    assert again.approver == "ops-lead"
    assert gate.list_pending() == ()


def test_an_approval_can_be_claimed_for_execution_exactly_once(gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)
    gate.approve(request.id, approver="ops-lead")

    executed = gate.claim_for_execution(request.id)

    assert executed.status is ApprovalStatus.EXECUTED
    with pytest.raises(ApprovalStateError):
        gate.claim_for_execution(request.id)
    assert gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD).status is ApprovalStatus.EXECUTED


def test_a_pending_request_cannot_be_claimed_for_execution(gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)

    with pytest.raises(ApprovalStateError):
        gate.claim_for_execution(request.id)


def test_a_denied_request_stays_denied_and_carries_the_note(gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)
    gate.deny(request.id, approver="ops-lead", note="insufficient evidence")

    denied = gate.get(request.id)

    assert denied.status is ApprovalStatus.DENIED
    assert denied.note == "insufficient evidence"
    with pytest.raises(ApprovalStateError):
        gate.approve(request.id, approver="someone-else")
    with pytest.raises(ApprovalStateError):
        gate.claim_for_execution(request.id)


def test_a_request_cannot_be_approved_twice(gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    gate.approve(request.id, approver="ops-lead")

    with pytest.raises(ApprovalStateError):
        gate.approve(request.id, approver="ops-lead")


def test_transitions_replace_the_request_instead_of_mutating_it(gate: ApprovalGate) -> None:
    pending = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    approved = gate.approve(pending.id, approver="ops-lead")

    assert pending.status is ApprovalStatus.PENDING
    assert approved.status is ApprovalStatus.APPROVED


@pytest.mark.parametrize("method", ["approve", "deny"])
def test_resolving_an_unknown_request_id_raises(gate: ApprovalGate, method: str) -> None:
    with pytest.raises(ApprovalNotFoundError):
        getattr(gate, method)("no-such-id", approver="ops-lead")


def test_getting_an_unknown_request_id_raises(gate: ApprovalGate) -> None:
    with pytest.raises(ApprovalNotFoundError):
        gate.get("no-such-id")


@pytest.mark.parametrize("decide", ["approve", "deny"])
def test_an_approvers_note_is_stored_without_pii(gate: ApprovalGate, decide: str) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    decided = getattr(gate, decide)(request.id, "alice", "called passenger on +49 30 1234 5678")

    assert decided.note == "called passenger on [PHONE]"
