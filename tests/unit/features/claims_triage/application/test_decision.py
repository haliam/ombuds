import pytest

from ombuds.domain.models.claim import EligibilityResult
from ombuds.features.claims_triage.application.decision import TriageDecision, verify_decision
from ombuds.platform.ai.schemas.structured_output import StructuredOutputError
from ombuds.platform.ai.schemas.tool_calls import ToolResult

_ELIGIBILITY = EligibilityResult(eligible=True, compensation_eur=250, reasons=("eligible",))


def _check_eligibility_result(result: EligibilityResult = _ELIGIBILITY, *, is_error: bool = False) -> ToolResult:
    return ToolResult(call_id="call-1", name="check_eligibility", content=result.model_dump_json(), is_error=is_error)


def test_verify_decision_accepts_a_decision_that_matches_check_eligibility() -> None:
    decision = TriageDecision(eligible=True, compensation_amount_eur=250, reason_codes=("eligible",), explanation="x")

    verify_decision(decision, [_check_eligibility_result()])  # does not raise


def test_verify_decision_rejects_a_decision_with_no_check_eligibility_call() -> None:
    decision = TriageDecision(eligible=True, compensation_amount_eur=250, reason_codes=("eligible",), explanation="x")

    with pytest.raises(StructuredOutputError, match="no successful check_eligibility result"):
        verify_decision(decision, [])


def test_verify_decision_ignores_a_failed_check_eligibility_call() -> None:
    decision = TriageDecision(eligible=True, compensation_amount_eur=250, reason_codes=("eligible",), explanation="x")

    with pytest.raises(StructuredOutputError, match="no successful check_eligibility result"):
        verify_decision(decision, [_check_eligibility_result(is_error=True)])


def test_verify_decision_uses_the_most_recent_check_eligibility_call() -> None:
    stale = EligibilityResult(eligible=False, compensation_eur=0, reasons=("out_of_scope",))
    decision = TriageDecision(eligible=True, compensation_amount_eur=250, reason_codes=("eligible",), explanation="x")

    verify_decision(decision, [_check_eligibility_result(stale), _check_eligibility_result(_ELIGIBILITY)])


def test_verify_decision_rejects_a_mismatched_eligible_flag() -> None:
    decision = TriageDecision(eligible=False, reason_codes=("eligible",), explanation="x")

    with pytest.raises(StructuredOutputError, match="does not match check_eligibility's eligible"):
        verify_decision(decision, [_check_eligibility_result()])


def test_verify_decision_rejects_a_mismatched_amount() -> None:
    decision = TriageDecision(eligible=True, compensation_amount_eur=999, reason_codes=("eligible",), explanation="x")

    with pytest.raises(StructuredOutputError, match="does not match check_eligibility's compensation_eur"):
        verify_decision(decision, [_check_eligibility_result()])


def test_verify_decision_treats_none_amount_as_zero_when_ineligible() -> None:
    ineligible = EligibilityResult(eligible=False, compensation_eur=0, reasons=("out_of_scope",))
    decision = TriageDecision(
        eligible=False, compensation_amount_eur=None, reason_codes=("out_of_scope",), explanation="x"
    )

    verify_decision(decision, [_check_eligibility_result(ineligible)])  # does not raise


def test_verify_decision_rejects_mismatched_reason_codes() -> None:
    decision = TriageDecision(eligible=True, compensation_amount_eur=250, reason_codes=("made_up",), explanation="x")

    with pytest.raises(StructuredOutputError, match="does not match check_eligibility's reasons"):
        verify_decision(decision, [_check_eligibility_result()])
