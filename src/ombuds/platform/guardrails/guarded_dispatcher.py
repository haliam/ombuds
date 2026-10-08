"""A `ToolDispatcher` wrapper that redacts PII from every tool call's arguments before dispatch.

Wraps any dispatcher — the in-process `ToolRegistry`, an `McpToolClient`, or another wrapper — so a model
(or an external MCP client) can't send personal data to a tool, e.g. in a `search_kb` query that is then
embedded by a third-party API. Tool results are not filtered: they come from our own typed tools.
"""

from collections.abc import Sequence

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.pii_filter import redact_value


class GuardedDispatcher:
    """Delegates to `inner` with PII redacted from each call's string arguments."""

    def __init__(self, inner: ToolDispatcher) -> None:
        self._inner = inner

    def definitions(self) -> Sequence[ToolDefinition]:
        return self._inner.definitions()

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        return self._inner.dispatch_all([self._scrub(call) for call in calls])

    @staticmethod
    def _scrub(call: ToolCall) -> ToolCall:
        arguments = redact_value(call.arguments)
        assert isinstance(arguments, dict)
        return call.model_copy(update={"arguments": arguments})
