"""An `LLMProvider` wrapper that opens one span per model turn (ADR-0017).

Wraps each concrete adapter, inside `FallbackProvider`, so a failover shows up as two sibling `llm.turn`
spans: the failed primary and the fallback that answered. Attributes are the model, the stop reason and the
number of tool calls requested; never the messages, system prompt or response text.
"""

from collections.abc import Iterator, Sequence

from opentelemetry.trace import Span

from ombuds.platform.ai.providers.base import LLMProvider, ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TurnDone
from ombuds.platform.observability.tracing import start_span, trace_stream

SPAN_NAME = "llm.turn"


class TracedProvider:
    """Delegates to `inner`, recording each `run_turn`/`stream_turn` as an `llm.turn` span tagged with `model`."""

    def __init__(self, inner: LLMProvider, model: str) -> None:
        self._inner = inner
        self._model = model

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        with start_span(SPAN_NAME, model=self._model, streaming=False) as span:
            turn = self._inner.run_turn(messages, tools, system=system)
            span.set_attribute("stop_reason", turn.stop_reason)
            span.set_attribute("tool_call_count", len(turn.tool_calls))
            return turn

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        return trace_stream(
            SPAN_NAME,
            iter(self._inner.stream_turn(messages, tools, system=system)),
            _record_done,
            model=self._model,
            streaming=True,
        )


def _record_done(span: Span, event: StreamEvent) -> None:
    if isinstance(event, TurnDone):
        span.set_attribute("stop_reason", event.stop_reason)
        span.set_attribute("tool_call_count", len(event.tool_calls))
