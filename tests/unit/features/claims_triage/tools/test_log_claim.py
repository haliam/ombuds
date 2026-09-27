import pytest

import ombuds.features.claims_triage.tools.log_claim as log_claim_module
from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL, LogClaimArgs, log_claim
from ombuds.features.claims_triage.verticals.airline.evidence_schema import DisruptionType, FlightDisruption
from ombuds.platform.guardrails.approval_gate import ApprovalDecision


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


def test_log_claim_is_denied_by_the_approval_gate_stub() -> None:
    result = log_claim(_args())

    assert result.logged is False
    assert "approval_gate stub" in result.reason


def test_log_claim_recomputes_eligibility_rather_than_trusting_the_caller() -> None:
    """log_claim takes flight facts, not an eligibility judgment — there is no eligibility field to trust
    or distrust; this pins that an out-of-scope disruption is still denied by the (deny-all) gate rather
    than short-circuiting on some caller-supplied verdict. See W1 review finding F-01."""
    result = log_claim(_args(departs_from_eu=False, arrives_in_eu=False))

    assert result.logged is False


def test_log_claim_raises_tool_execution_error_once_approved(monkeypatch) -> None:
    """Persistence isn't implemented yet — an approved decision must raise ToolExecutionError, not crash
    the triage turn with NotImplementedError (see ToolRegistry.dispatch)."""
    monkeypatch.setattr(
        log_claim_module, "check_approval", lambda action: ApprovalDecision(approved=True, reason="approved")
    )

    with pytest.raises(ToolExecutionError, match="not implemented"):
        log_claim(_args())


def test_log_claim_args_requires_nonempty_claim_id() -> None:
    with pytest.raises(ValueError):
        LogClaimArgs(claim_id="", disruption=_disruption())


def test_tool_definition_args_model_is_log_claim_args() -> None:
    assert LOG_CLAIM_TOOL.args_model is LogClaimArgs
