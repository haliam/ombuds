import pytest

from ombuds.features.claims_triage.application.triage_use_case import MAX_TOOL_TURNS, run_triage
from ombuds.platform.ai.providers.base import ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition


class _FakeProvider:
    """Replays a fixed sequence of turns, ignoring what it's actually sent — no real API calls."""

    def __init__(self, turns: list[ProviderTurn]) -> None:
        self._turns = list(turns)
        self.calls = 0

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        self.calls += 1
        return self._turns.pop(0)


def _disruption_args() -> dict[str, object]:
    return {
        "disruption": "cancellation",
        "distance_km": 1200,
        "intra_eu": True,
        "departs_from_eu": True,
        "arrives_in_eu": True,
        "eu_carrier": True,
    }


def test_run_triage_returns_final_answer_when_the_model_calls_no_tools() -> None:
    provider = _FakeProvider(
        [ProviderTurn(text="Please provide your flight details.", tool_calls=(), stop_reason="end_turn", content=[])]
    )

    result = run_triage("My flight was delayed.", provider=provider)

    assert result.answer == "Please provide your flight details."
    assert result.tool_results == ()
    assert provider.calls == 1


def test_run_triage_dispatches_a_tool_call_and_feeds_the_result_back() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text="You are eligible for EUR 250.", tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    result = run_triage("My flight from Berlin to Lisbon was cancelled.", provider=provider)

    assert result.answer == "You are eligible for EUR 250."
    assert len(result.tool_results) == 1
    assert result.tool_results[0].name == "check_eligibility"
    assert result.tool_results[0].is_error is False
    assert provider.calls == 2


def test_run_triage_reports_an_unknown_tool_as_an_error_result_without_crashing() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="nonexistent", arguments={}),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text="Sorry, something went wrong.", tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    result = run_triage("claim", provider=provider)

    assert result.tool_results[0].is_error is True
    assert "unknown tool" in result.tool_results[0].content


def test_run_triage_gives_up_after_max_tool_turns() -> None:
    looping_turn = ProviderTurn(
        text="",
        tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
        stop_reason="tool_use",
        content=[],
    )
    provider = _FakeProvider([looping_turn] * MAX_TOOL_TURNS)

    with pytest.raises(RuntimeError, match="did not converge"):
        run_triage("claim", provider=provider)
