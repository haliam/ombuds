from collections.abc import Iterator, Sequence

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from ombuds.platform.ai.providers.base import ProviderTurn, ProviderUnavailableError
from ombuds.platform.ai.providers.traced import TracedProvider
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TextDelta, TurnDone

_CALL = ToolCall(id="1", name="search_kb", arguments={"query": "jane@example.com"})
_TURN = ProviderTurn(text="private text", tool_calls=(_CALL,), stop_reason="tool_use", content=[])


class _Provider:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        if self._error:
            raise self._error
        return _TURN

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        yield TextDelta(text="private text")
        yield TurnDone(text="private text", tool_calls=(_CALL,), stop_reason="tool_use", content=[])


def test_run_turn_is_one_span_with_model_and_outcome_but_no_content(spans: InMemorySpanExporter) -> None:
    turn = TracedProvider(_Provider(), "m-1").run_turn([{"role": "user", "content": "hi"}], [], system="s")

    assert turn is _TURN
    (span,) = spans.get_finished_spans()
    assert span.name == "llm.turn"
    assert dict(span.attributes or {}) == {
        "model": "m-1",
        "streaming": False,
        "stop_reason": "tool_use",
        "tool_call_count": 1,
    }


def test_a_provider_failure_marks_the_span_as_error(spans: InMemorySpanExporter) -> None:
    with pytest.raises(ProviderUnavailableError):
        TracedProvider(_Provider(ProviderUnavailableError("down")), "m-1").run_turn([], [], system="s")

    (span,) = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "ProviderUnavailableError"


def test_stream_turn_yields_every_event_in_one_span(spans: InMemorySpanExporter) -> None:
    events = list(TracedProvider(_Provider(), "m-1").stream_turn([], [], system="s"))

    assert [type(e) for e in events] == [TextDelta, TurnDone]
    (span,) = spans.get_finished_spans()
    assert dict(span.attributes or {}) == {
        "model": "m-1",
        "streaming": True,
        "stop_reason": "tool_use",
        "tool_call_count": 1,
    }
