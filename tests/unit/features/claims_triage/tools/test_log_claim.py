import pytest

from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL, LogClaimArgs, log_claim
from ombuds.features.claims_triage.verticals.airline.evidence_schema import DisruptionType, FlightDisruption
from ombuds.platform.guardrails.approval_gate import ApprovalGate, ApprovalStatus


@pytest.fixture
def gate() -> ApprovalGate:
    return ApprovalGate()


def _disruption(**overrides) -> FlightDisruption:
    """Baseline: in-scope 1200 km intra-EU cancellation with no notice — eligible for EUR 250."""
    fields = dict(
        disruption=DisruptionType.CANCELLATION,
        distance_km=1200,
        intra_eu=True,
        departs_from_eu=True,
        arrives_in_eu=True,
        eu_carrier=True,
    )
    return FlightDisruption(**(fields | overrides))


def _args(**overrides) -> LogClaimArgs:
    return LogClaimArgs(claim_id="claim-1", disruption=_disruption(**overrides))


def test_log_claim_submits_a_pending_request_instead_of_recording(gate: ApprovalGate) -> None:
    result = log_claim(_args(), gate)

    assert result.status is ApprovalStatus.PENDING
    assert "submitted for human approval" in result.reason
    assert gate.list_pending()[0].id == result.approval_request_id


def test_the_approval_payload_is_the_rules_derived_outcome_and_the_facts(gate: ApprovalGate) -> None:
    """What the human approves is the rules engine's output for these facts, never a model-supplied verdict.
    See W1 review F-01 and ADR-0009."""
    result = log_claim(_args(), gate)

    payload = gate.get(result.approval_request_id).payload
    assert payload["claim_id"] == "claim-1"
    assert payload["eligible"] is True
    assert payload["compensation_eur"] == 250
    assert payload["reasons"] == ["eligible"]
    assert payload["facts"] == _disruption().model_dump(mode="json")


def test_different_facts_for_the_same_claim_are_a_separate_request(gate: ApprovalGate) -> None:
    first = log_claim(_args(), gate)
    gate.approve(first.approval_request_id, approver="ops-lead")

    second = log_claim(_args(distance_km=3600), gate)

    assert second.approval_request_id != first.approval_request_id
    assert second.status is ApprovalStatus.PENDING


def test_resubmitting_the_same_facts_reports_the_existing_requests_status(gate: ApprovalGate) -> None:
    first = log_claim(_args(), gate)
    gate.approve(first.approval_request_id, approver="ops-lead")
    gate.claim_for_execution(first.approval_request_id)

    again = log_claim(_args(), gate)

    assert again.approval_request_id == first.approval_request_id
    assert again.status is ApprovalStatus.EXECUTED
    assert again.reason == "already recorded"


def test_log_claim_args_requires_nonempty_claim_id() -> None:
    with pytest.raises(ValueError):
        LogClaimArgs(claim_id="", disruption=_disruption())


def test_tool_definition_args_model_is_log_claim_args() -> None:
    assert LOG_CLAIM_TOOL.args_model is LogClaimArgs
