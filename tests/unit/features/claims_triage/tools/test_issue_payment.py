import pytest

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.tools.issue_payment import ISSUE_PAYMENT_TOOL, IssuePaymentArgs, issue_payment
from ombuds.features.claims_triage.verticals.airline.evidence_schema import DisruptionType, FlightDisruption
from ombuds.platform.guardrails.approval_gate import ApprovalGate, ApprovalStatus
from tests.fakes import InMemoryClaims


@pytest.fixture
def gate() -> ApprovalGate:
    return ApprovalGate()


@pytest.fixture
def claims() -> InMemoryClaims:
    """Claim `claim-1` already logged with the baseline EUR 250 compensation."""
    logged = InMemoryClaims()
    logged.record("claim-1", {}, {"eligible": True, "compensation_eur": 250, "reasons": []})
    return logged


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


def _args(**overrides) -> IssuePaymentArgs:
    return IssuePaymentArgs(claim_id="claim-1", disruption=_disruption(**overrides))


def test_issue_payment_submits_a_pending_request_instead_of_paying(gate: ApprovalGate, claims: InMemoryClaims) -> None:
    result = issue_payment(_args(), gate, claims)

    assert result.status is ApprovalStatus.PENDING
    assert gate.list_pending()[0].id == result.approval_request_id


def test_the_amount_comes_from_the_rules_engine_not_the_caller(gate: ApprovalGate, claims: InMemoryClaims) -> None:
    """A caller-supplied amount can't reach the approver: the args carry no amount at all, and anything
    extra (e.g. a model-invented `amount_eur`) is ignored. See agent-loop review F-04."""
    args = IssuePaymentArgs.model_validate(
        {"claim_id": "claim-1", "amount_eur": 9999, "disruption": _disruption().model_dump(mode="json")}
    )

    result = issue_payment(args, gate, claims)

    assert result.amount_eur == 250
    assert gate.get(result.approval_request_id).payload["amount_eur"] == 250


def test_issue_payment_refuses_a_claim_with_no_compensation_due(gate: ApprovalGate, claims: InMemoryClaims) -> None:
    with pytest.raises(ToolExecutionError, match="not entitled to compensation"):
        issue_payment(_args(extraordinary_circumstances=True), gate, claims)

    assert gate.list_pending() == ()


def test_issue_payment_args_requires_nonempty_claim_id() -> None:
    with pytest.raises(ValueError):
        IssuePaymentArgs(claim_id="", disruption=_disruption())


def test_tool_definition_args_model_is_issue_payment_args() -> None:
    assert ISSUE_PAYMENT_TOOL.args_model is IssuePaymentArgs


def test_issue_payment_refuses_a_claim_that_was_never_logged(gate: ApprovalGate) -> None:
    with pytest.raises(ToolExecutionError, match="has not been logged"):
        issue_payment(_args(), gate, InMemoryClaims())

    assert gate.list_pending() == ()


def test_issue_payment_refuses_an_amount_that_differs_from_the_logged_decision(gate: ApprovalGate) -> None:
    logged = InMemoryClaims()
    logged.record("claim-1", {}, {"eligible": True, "compensation_eur": 400, "reasons": []})

    with pytest.raises(ToolExecutionError, match="logged with compensation 400 EUR"):
        issue_payment(_args(), gate, logged)

    assert gate.list_pending() == ()
