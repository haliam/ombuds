from collections.abc import Sequence

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.observability.traced_dispatcher import TracedDispatcher


class _Dispatcher:
    def definitions(self) -> Sequence[ToolDefinition]:
        return []

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        return [ToolResult(call_id=c.id, name=c.name, content="secret", is_error=c.name == "bad") for c in calls]


def test_one_span_per_call_with_outcome_and_no_arguments_or_result(spans: InMemorySpanExporter) -> None:
    calls = [
        ToolCall(id="1", name="search_kb", arguments={"query": "jane@example.com"}),
        ToolCall(id="2", name="bad", arguments={"claim_id": "c-1"}),
    ]

    results = TracedDispatcher(_Dispatcher()).dispatch_all(calls)

    assert [r.call_id for r in results] == ["1", "2"]
    finished = spans.get_finished_spans()
    assert [s.name for s in finished] == ["tool.search_kb", "tool.bad"]
    assert dict(finished[0].attributes or {}) == {"tool.name": "search_kb", "tool.call_id": "1", "tool.outcome": "ok"}
    assert dict(finished[1].attributes or {}) == {
        "tool.name": "bad",
        "tool.call_id": "2",
        "claim_id": "c-1",
        "tool.outcome": "error",
    }
