import pytest
from pydantic import ValidationError

from evals.agent_dataset import AgentCase, load_cases
from ombuds.platform.guardrails.injection_detection import detect


def test_the_shipped_dataset_loads_and_covers_every_outcome():
    cases = load_cases()
    assert len(cases) >= 15
    assert {case.outcome for case in cases} == {"decision", "clarify", "escalate"}


def test_the_decision_cases_span_eligible_and_ineligible_verdicts():
    verdicts = [case.expected() for case in load_cases() if case.outcome == "decision"]
    assert any(v is not None and v.eligible for v in verdicts)
    assert any(v is not None and not v.eligible for v in verdicts)


def test_escalate_cases_are_caught_by_the_injection_detector():
    """An `escalate` case that the detector does not flag would reach the model and measure nothing."""
    for case in load_cases():
        if case.outcome == "escalate":
            assert detect(case.claim).suspicious, case.id


def test_clarify_cases_are_not_flagged_as_injection():
    for case in load_cases():
        if case.outcome == "clarify":
            assert not detect(case.claim).suspicious, case.id


def test_a_decision_case_without_facts_is_rejected():
    with pytest.raises(ValidationError):
        AgentCase(id="x", claim="c", outcome="decision")


def test_a_clarify_case_with_facts_is_rejected():
    facts = {
        "disruption": "delay",
        "distance_km": 500,
        "intra_eu": True,
        "departs_from_eu": True,
        "arrives_in_eu": True,
        "eu_carrier": True,
    }
    with pytest.raises(ValidationError):
        AgentCase.model_validate({"id": "x", "claim": "c", "outcome": "clarify", "facts": facts})


def test_duplicate_ids_are_rejected(tmp_path):
    row = '{"id": "a", "claim": "c", "outcome": "clarify"}\n'
    path = tmp_path / "cases.jsonl"
    path.write_text(row + row)
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(path)
