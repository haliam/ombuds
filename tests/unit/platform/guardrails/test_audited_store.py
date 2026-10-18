import pytest
from pydantic import JsonValue

from ombuds.platform.guardrails.approval_gate import ApprovalGate, ApprovalStateError, GuardedAction
from ombuds.platform.guardrails.audit_log import AuditKind
from ombuds.platform.guardrails.audited_store import AuditedApprovalStore
from tests.unit.platform.guardrails.audit_fakes import RecordingAuditLog

_PAYMENT: dict[str, JsonValue] = {"claim_id": "c-1", "amount_eur": 250, "facts": {"secret": "raw"}}


def test_each_transition_is_recorded_once_with_the_request_and_claim_ids() -> None:
    audit = RecordingAuditLog()
    store = AuditedApprovalStore(ApprovalGate(), audit)

    request = store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)
    store.approve(request.id, "alice", "looks fine")
    store.claim_for_execution(request.id)

    assert [(e.kind, e.outcome) for e in audit.events] == [
        (AuditKind.APPROVAL_SUBMITTED, "pending"),
        (AuditKind.APPROVAL_APPROVED, "approved"),
        (AuditKind.APPROVAL_EXECUTED, "executed"),
    ]
    identities = {(e.subject, e.claim_id, e.approval_request_id) for e in audit.events}
    assert identities == {("issue_payment", "c-1", request.id)}
    assert audit.events[1].detail == {"approver": "alice"}


def test_a_denial_is_recorded_with_the_approver() -> None:
    audit = RecordingAuditLog()
    store = AuditedApprovalStore(ApprovalGate(), audit)
    request = store.submit(GuardedAction.LOG_CLAIM, {"claim_id": "c-2"})

    store.deny(request.id, "bob")

    assert (audit.events[-1].kind, audit.events[-1].detail) == (AuditKind.APPROVAL_DENIED, {"approver": "bob"})


def test_payloads_and_notes_are_never_copied_into_the_log() -> None:
    audit = RecordingAuditLog()
    store = AuditedApprovalStore(ApprovalGate(), audit)
    request = store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)

    store.approve(request.id, "alice", "call me on 555 123 4567")

    dumped = " ".join(event.model_dump_json() for event in audit.events)
    assert "raw" not in dumped and "555" not in dumped


def test_a_rejected_transition_records_nothing() -> None:
    audit = RecordingAuditLog()
    store = AuditedApprovalStore(ApprovalGate(), audit)
    request = store.submit(GuardedAction.LOG_CLAIM, {"claim_id": "c-3"})
    store.deny(request.id, "bob")
    recorded = len(audit.events)

    with pytest.raises(ApprovalStateError):
        store.approve(request.id, "alice")

    assert len(audit.events) == recorded
