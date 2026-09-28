import uuid
from collections.abc import Iterator, Sequence

import pytest

from ombuds.config import load_prompt
from ombuds.features.claims_triage.agent.memory.long_term import InMemoryLongTermMemoryStore
from ombuds.features.claims_triage.agent.nodes.escalate_retry import ESCALATION_ANSWER
from ombuds.features.claims_triage.application.triage_use_case import (
    MAX_REPAIR_ATTEMPTS,
    MAX_TOOL_TURNS,
    run_triage,
    stream_triage,
)
from ombuds.features.claims_triage.tools import log_claim as log_claim_module
from ombuds.platform.ai.providers.base import ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TextDelta, ToolCallDelta, ToolResultEvent, TurnDone
from ombuds.platform.guardrails.approval_gate import ApprovalDecision, GuardedAction

_DECISION_JSON = (
    '{"eligible": true, "compensation_amount_eur": 250, "reason_codes": ["eligible"], '
    '"explanation": "You are eligible for EUR 250."}'
)
# Schema-valid, but disagrees with what check_eligibility actually returns for `_disruption_args()`
# (eligible=True, compensation_eur=250, reasons=("eligible",)) — used to exercise verify_decision's
# repair path, as opposed to _parse_final_turn's shape-only validation.
_WRONG_DECISION_JSON = (
    '{"eligible": true, "compensation_amount_eur": 999, "reason_codes": ["eligible"], '
    '"explanation": "You are eligible for EUR 999."}'
)


class _FakeProvider:
    """Replays a fixed sequence of turns, ignoring what it's actually sent — no real API calls."""

    def __init__(self, turns: list[ProviderTurn]) -> None:
        self._turns = list(turns)
        self.calls = 0
        self.systems: list[str] = []
        self.messages: list[list[dict[str, object]]] = []

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        self.calls += 1
        self.systems.append(system)
        self.messages.append(list(messages))
        return self._turns.pop(0)

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        turn = self._turns.pop(0)
        if turn.text:
            yield TextDelta(text=turn.text)
        for call in turn.tool_calls:
            yield ToolCallDelta(call=call)
        yield TurnDone(text=turn.text, tool_calls=turn.tool_calls, stop_reason=turn.stop_reason, content=turn.content)


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
    assert result.decision is None
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
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    result = run_triage("My flight from Berlin to Lisbon was cancelled.", provider=provider)

    assert result.decision is not None
    assert result.decision.eligible is True
    assert result.decision.compensation_amount_eur == 250
    assert result.decision.reason_codes == ("eligible",)
    assert len(result.tool_results) == 1
    assert result.tool_results[0].name == "check_eligibility"
    assert result.tool_results[0].is_error is False
    assert provider.calls == 2


def test_run_triage_repairs_an_invalid_final_reply_and_returns_the_corrected_decision() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text='{"eligible": true}', tool_calls=(), stop_reason="end_turn", content=[]),
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    result = run_triage("claim", provider=provider)

    assert result.decision is not None
    assert result.decision.eligible is True
    assert provider.calls == 3


def test_run_triage_escalates_after_max_repair_attempts() -> None:
    provider = _FakeProvider(
        [ProviderTurn(text='{"eligible": true}', tool_calls=(), stop_reason="end_turn", content=[])]
        * (MAX_REPAIR_ATTEMPTS + 1)
    )

    result = run_triage("claim", provider=provider)

    assert result.escalated is True
    assert result.decision is None
    assert result.answer == ESCALATION_ANSWER
    assert result.escalation_reason is not None
    assert "does not match the required schema" in result.escalation_reason


def test_run_triage_repairs_a_decision_that_disagrees_with_check_eligibility() -> None:
    """A schema-valid decision that disagrees with check_eligibility's own result must be repaired, not
    trusted — the LLM is never the source of truth for eligibility or the amount. See F-01."""
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text=_WRONG_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    result = run_triage("claim", provider=provider)

    assert result.decision is not None
    assert result.decision.compensation_amount_eur == 250
    assert provider.calls == 3


def test_run_triage_escalates_after_max_repair_attempts_for_a_persistent_mismatch() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            *(
                ProviderTurn(text=_WRONG_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[])
                for _ in range(MAX_REPAIR_ATTEMPTS + 1)
            ),
        ]
    )

    result = run_triage("claim", provider=provider)

    assert result.escalated is True
    assert result.decision is None
    assert result.answer == ESCALATION_ANSWER
    assert "999" not in result.answer
    assert result.escalation_reason is not None
    assert "does not match check_eligibility" in result.escalation_reason


def test_run_triage_repairs_a_decision_given_without_calling_check_eligibility_first() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    result = run_triage("claim", provider=provider)

    assert result.decision is not None
    assert provider.calls == 3


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


def test_run_triage_escalates_after_max_tool_turns() -> None:
    looping_turn = ProviderTurn(
        text="Let me check that for you.",
        tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
        stop_reason="tool_use",
        content=[],
    )
    provider = _FakeProvider([looping_turn] * MAX_TOOL_TURNS)

    result = run_triage("claim", provider=provider)

    assert result.escalated is True
    assert result.decision is None
    assert result.answer == ESCALATION_ANSWER
    assert result.escalation_reason is not None
    assert "did not converge" in result.escalation_reason


def test_run_triage_escalates_on_an_unrecoverable_stop_reason() -> None:
    provider = _FakeProvider(
        [ProviderTurn(text="partial answer trunc", tool_calls=(), stop_reason="max_tokens", content=[])]
    )

    result = run_triage("claim", provider=provider)

    assert result.escalated is True
    assert result.decision is None
    assert result.answer == ESCALATION_ANSWER
    assert "partial answer trunc" not in result.answer
    assert result.escalation_reason is not None
    assert "max_tokens" in result.escalation_reason


def test_run_triage_saves_the_decision_to_long_term_memory_when_a_claimant_id_is_given() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )
    store = InMemoryLongTermMemoryStore()

    run_triage("claim", provider=provider, claimant_id="claimant@example.com", long_term_store=store)

    memory = store.load("claimant@example.com")
    assert memory.facts == {"last_eligible": "True", "last_compensation_eur": "250", "last_reasons": "eligible"}
    assert "You are eligible" not in str(memory.facts)


def test_run_triage_carries_prior_long_term_memory_into_a_later_run_for_the_same_claimant() -> None:
    store = InMemoryLongTermMemoryStore()
    first_provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )
    run_triage("claim", provider=first_provider, claimant_id="claimant@example.com", long_term_store=store)

    second_provider = _FakeProvider(
        [ProviderTurn(text="Please provide your flight details.", tool_calls=(), stop_reason="end_turn", content=[])]
    )
    run_triage("second claim", provider=second_provider, claimant_id="claimant@example.com", long_term_store=store)

    first_message = second_provider.messages[0][0]
    assert "last_compensation_eur: 250" in str(first_message["content"])
    assert "second claim" in str(first_message["content"])
    assert second_provider.systems[0] == load_prompt("claims_triage")


def test_run_triage_does_not_touch_long_term_memory_without_a_claimant_id() -> None:
    provider = _FakeProvider(
        [ProviderTurn(text="Please provide your flight details.", tool_calls=(), stop_reason="end_turn", content=[])]
    )
    store = InMemoryLongTermMemoryStore()

    run_triage("claim", provider=provider, long_term_store=store)

    assert provider.messages[0][0] == {"role": "user", "content": "claim"}
    assert store.load("claimant@example.com").facts == {}


def test_run_triage_keeps_the_system_prompt_constant_and_free_of_tool_output() -> None:
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(text=_DECISION_JSON, tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    run_triage("claim", provider=provider)

    assert provider.systems == [load_prompt("claims_triage")] * 2


def test_stream_triage_yields_text_delta_and_turn_done_when_no_tools_are_called() -> None:
    provider = _FakeProvider(
        [ProviderTurn(text="Please provide your flight details.", tool_calls=(), stop_reason="end_turn", content=[])]
    )

    events = list(stream_triage("My flight was delayed.", provider=provider))

    assert events[0] == TextDelta(text="Please provide your flight details.")
    final = events[-1]
    assert isinstance(final, TurnDone)
    assert final.text == "Please provide your flight details."
    assert final.tool_calls == ()


def test_stream_triage_emits_tool_call_and_tool_result_events() -> None:
    call = ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args())
    provider = _FakeProvider(
        [
            ProviderTurn(text="", tool_calls=(call,), stop_reason="tool_use", content=[]),
            ProviderTurn(text="You are eligible for EUR 250.", tool_calls=(), stop_reason="end_turn", content=[]),
        ]
    )

    events = list(stream_triage("My flight from Berlin to Lisbon was cancelled.", provider=provider))

    tool_call_events = [event for event in events if isinstance(event, ToolCallDelta)]
    result_events = [event for event in events if isinstance(event, ToolResultEvent)]
    assert tool_call_events == [ToolCallDelta(call=call)]
    assert len(result_events) == 1
    assert result_events[0].result.name == "check_eligibility"
    assert result_events[0].result.is_error is False
    assert provider.calls == 2


def test_stream_triage_gives_up_after_max_tool_turns() -> None:
    looping_turn = ProviderTurn(
        text="",
        tool_calls=(ToolCall(id="call-1", name="check_eligibility", arguments=_disruption_args()),),
        stop_reason="tool_use",
        content=[],
    )
    provider = _FakeProvider([looping_turn] * MAX_TOOL_TURNS)

    with pytest.raises(RuntimeError, match="did not converge"):
        list(stream_triage("claim", provider=provider))


def test_run_triage_issues_a_claim_id_when_none_is_given() -> None:
    provider = _FakeProvider(
        [ProviderTurn(text="Please provide your flight details.", tool_calls=(), stop_reason="end_turn", content=[])]
    )

    result = run_triage("claim", provider=provider)

    assert uuid.UUID(result.claim_id)


def test_run_triage_binds_log_claim_to_the_server_issued_claim_id(monkeypatch) -> None:
    """A claim_id the model invents (or is steered into by the claim text) never reaches the approval gate."""
    seen_contexts: list[object] = []

    def _fake_check_approval(action: GuardedAction, context: object = None) -> ApprovalDecision:
        seen_contexts.append(context)
        return ApprovalDecision(approved=False, reason="awaiting human approval", request_id="req-1")

    monkeypatch.setattr(log_claim_module, "check_approval", _fake_check_approval)
    provider = _FakeProvider(
        [
            ProviderTurn(
                text="",
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="log_claim",
                        arguments={"claim_id": "CLM-FROM-MODEL", "disruption": _disruption_args()},
                    ),
                ),
                stop_reason="tool_use",
                content=[],
            ),
            ProviderTurn(
                text="Your claim was submitted for review.", tool_calls=(), stop_reason="end_turn", content=[]
            ),
        ]
    )

    result = run_triage("claim", claim_id="CLM-SERVER", provider=provider)

    assert result.claim_id == "CLM-SERVER"
    assert len(seen_contexts) == 1
    assert "CLM-SERVER" in str(seen_contexts[0])
    assert "CLM-FROM-MODEL" not in str(seen_contexts[0])
