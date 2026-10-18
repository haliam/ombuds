"""A `ToolDispatcher` wrapper that opens one span per tool call (ADR-0017).

Sits outside `AuditedDispatcher`, so the span is still active when the audit row is written and the row's
`trace_id` points at it. The span carries the tool name, call id, claim id and `ok`/`error` outcome; never
the arguments or the result.
"""

from collections.abc import Sequence

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.observability.tracing import start_span

SPAN_PREFIX = "tool."


class TracedDispatcher:
    """Delegates each call to `inner` one at a time so each gets its own `tool.<name>` span."""

    def __init__(self, inner: ToolDispatcher) -> None:
        self._inner = inner

    def definitions(self) -> Sequence[ToolDefinition]:
        return self._inner.definitions()

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        return [self._dispatch_one(call) for call in calls]

    def _dispatch_one(self, call: ToolCall) -> ToolResult:
        claim_id = call.arguments.get("claim_id")
        attributes: dict[str, str | int | bool] = {"tool.name": call.name, "tool.call_id": call.id}
        if isinstance(claim_id, str):
            attributes["claim_id"] = claim_id
        with start_span(f"{SPAN_PREFIX}{call.name}", **attributes) as span:
            (result,) = self._inner.dispatch_all([call])
            span.set_attribute("tool.outcome", "error" if result.is_error else "ok")
            return result
