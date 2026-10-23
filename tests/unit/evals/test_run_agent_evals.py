from evals.agent_dataset import AgentCase
from evals.run_agent_evals import report, run_case, score_case
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.features.claims_triage.application.triage_use_case import TriageResult
from ombuds.platform.ai.schemas.tool_calls import ToolResult

FACTS = {
    "disruption": "delay",
    "distance_km": 1870,
    "intra_eu": True,
    "departs_from_eu": True,
    "arrives_in_eu": True,
    "eu_carrier": True,
    "arrival_delay": "PT4H",
}
DECISION_CASE = AgentCase.model_validate({"id": "d", "claim": "c", "outcome": "decision", "facts": FACTS})
CLARIFY_CASE = AgentCase(id="q", claim="c", outcome="clarify")
ESCALATE_CASE = AgentCase(id="e", claim="c", outcome="escalate")
ELIGIBILITY_CALL = ToolResult(call_id="1", name="check_eligibility", content="{}")


def _result(
    decision: TriageDecision | None = None, *, escalated: bool = False, tools: tuple[ToolResult, ...] = ()
) -> TriageResult:
    return TriageResult(
        claim_id="c",
        answer="a",
        decision=decision,
        tool_results=tools,
        escalated=escalated,
        escalation_reason="why" if escalated else None,
    )


def _decision(*, eligible: bool = True, amount: int | None = 400, reasons: tuple[str, ...] = ("eligible",)):
    return TriageDecision(eligible=eligible, compensation_amount_eur=amount, reason_codes=reasons, explanation="x")


def test_a_decision_matching_the_rules_engine_scores_fully():
    score = score_case(DECISION_CASE, _result(_decision(), tools=(ELIGIBILITY_CALL,)))
    assert score.outcome_ok and score.verdict_ok and score.called_eligibility


def test_a_decision_with_the_wrong_amount_has_the_right_outcome_but_a_wrong_verdict():
    score = score_case(DECISION_CASE, _result(_decision(amount=250), tools=(ELIGIBILITY_CALL,)))
    assert score.outcome_ok
    assert score.verdict_ok is False
    assert "expected True/400" in score.detail


def test_asking_a_question_when_a_decision_was_expected_is_an_outcome_miss():
    score = score_case(DECISION_CASE, _result())
    assert not score.outcome_ok
    assert score.actual == "clarify"
    assert score.verdict_ok is False


def test_clarify_and_escalate_cases_have_no_verdict():
    clarify = score_case(CLARIFY_CASE, _result())
    escalate = score_case(ESCALATE_CASE, _result(escalated=True))
    assert clarify.outcome_ok and clarify.verdict_ok is None
    assert escalate.outcome_ok and escalate.verdict_ok is None


def test_a_raised_error_becomes_an_error_score():
    def boom(_claim: str) -> TriageResult:
        raise RuntimeError("cap reached")

    score = run_case(DECISION_CASE, boom)
    assert score.actual == "error"
    assert not score.outcome_ok
    assert "RuntimeError: cap reached" in score.detail


def test_report_summarises_and_lists_the_misses():
    scores = [
        score_case(DECISION_CASE, _result(_decision(), tools=(ELIGIBILITY_CALL,))),
        score_case(CLARIFY_CASE, _result(_decision())),
    ]
    text = report(scores)
    assert "outcome correct:   1/2" in text
    assert "verdict correct:   1/1" in text
    assert "q: expected clarify, got decision" in text


def test_report_says_none_when_every_case_passes():
    text = report([score_case(CLARIFY_CASE, _result())])
    assert "  none" in text
