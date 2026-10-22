from collections.abc import Mapping

import pytest
from pydantic import JsonValue

from ombuds.domain.errors import PolicyDeniedError, ToolExecutionError
from ombuds.platform.guardrails.approval_gate import ApprovalGate, ApprovalStatus, GuardedAction
from ombuds.platform.guardrails.audit_log import AuditKind
from ombuds.platform.guardrails.policy_checked_store import PolicyCheckedApprovalStore
from ombuds.platform.guardrails.policy_engine import PolicyDecision
from tests.unit.platform.guardrails.audit_fakes import RecordingAuditLog
from tests.unit.platform.guardrails.store_fakes import executing

_PAYMENT: dict[str, JsonValue] = {"claim_id": "c-1", "amount_eur": 250}


class _FakeEngine:
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        self.inputs: list[Mapping[str, JsonValue]] = []

    def evaluate(self, policy_input: Mapping[str, JsonValue]) -> PolicyDecision:
        self.inputs.append(policy_input)
        return self.decision


def _store(
    decision: PolicyDecision, audit: RecordingAuditLog | None = None
) -> tuple[PolicyCheckedApprovalStore, ApprovalGate, _FakeEngine]:
    gate, engine = ApprovalGate(), _FakeEngine(decision)
    return (
        PolicyCheckedApprovalStore(executing(gate), engine, {"max_payout_eur": 400}, audit or RecordingAuditLog()),
        gate,
        engine,
    )


def test_an_allowed_submission_becomes_a_pending_request() -> None:
    store, gate, _ = _store(PolicyDecision(allow=True))

    request = store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)

    assert request.status is ApprovalStatus.PENDING
    assert gate.list_pending() == (request,)


def test_a_denied_submission_raises_with_the_reasons_and_creates_no_request() -> None:
    store, gate, _ = _store(PolicyDecision(allow=False, reasons=("payout_above_limit",)))

    with pytest.raises(PolicyDeniedError) as denied:
        store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)

    assert denied.value.reasons == ("payout_above_limit",)
    assert gate.list_pending() == ()


def test_a_policy_denial_reaches_tool_callers_as_a_tool_error() -> None:
    assert issubclass(PolicyDeniedError, ToolExecutionError)


def test_the_policy_is_asked_about_the_action_the_payload_and_the_configured_limit() -> None:
    store, _, engine = _store(PolicyDecision(allow=True))

    store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)

    assert engine.inputs == [{"action": "issue_payment", "payload": _PAYMENT, "limits": {"max_payout_eur": 400}}]


def test_approving_and_denying_do_not_consult_the_policy() -> None:
    store, _, engine = _store(PolicyDecision(allow=True))
    first = store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)
    second = store.submit(GuardedAction.LOG_CLAIM, {"claim_id": "c-2"})
    engine.inputs.clear()

    assert store.approve(first.id, "alice").status is ApprovalStatus.EXECUTED
    assert store.deny(second.id, "alice").status is ApprovalStatus.DENIED
    assert engine.inputs == []


def test_every_verdict_is_audited_with_its_reasons_and_policy_version() -> None:
    audit = RecordingAuditLog()
    allowed, _, _ = _store(PolicyDecision(allow=True, policy_version="v1"), audit)
    denied, _, _ = _store(PolicyDecision(allow=False, reasons=("payout_above_limit",), policy_version="v1"), audit)

    allowed.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)
    with pytest.raises(PolicyDeniedError):
        denied.submit(GuardedAction.ISSUE_PAYMENT, {"claim_id": "c-9", "amount_eur": 600})

    assert [(e.kind, e.outcome, e.claim_id, e.detail) for e in audit.events] == [
        (AuditKind.POLICY_DECISION, "allow", "c-1", {"reasons": [], "policy_version": "v1"}),
        (
            AuditKind.POLICY_DECISION,
            "deny",
            "c-9",
            {"reasons": ["payout_above_limit"], "policy_version": "v1"},
        ),
    ]


def test_policy_check_is_a_span_carrying_the_verdict(spans) -> None:
    store, _, _ = _store(PolicyDecision(allow=False, reasons=("over_limit",), policy_version="v1"))

    with pytest.raises(PolicyDeniedError):
        store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)

    (span,) = spans.get_finished_spans()
    assert span.name == "policy.check"
    assert dict(span.attributes or {}) == {
        "action": GuardedAction.ISSUE_PAYMENT.value,
        "policy.decision": "deny",
        "policy.version": "v1",
    }


def test_execute_approved_delegates_without_consulting_the_policy() -> None:
    store, gate, engine = _store(PolicyDecision(allow=True))
    request = store.submit(GuardedAction.ISSUE_PAYMENT, _PAYMENT)
    gate.approve(request.id, "alice")
    engine.inputs.clear()

    assert store.execute_approved(request.id).status is ApprovalStatus.EXECUTED
    assert engine.inputs == []
