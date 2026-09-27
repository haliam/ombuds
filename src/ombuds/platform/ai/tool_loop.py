"""Parses a provider's tool-use requests and dispatches each one to a registered handler.

Provider-agnostic: it operates on `ToolCall`/`ToolResult` (platform/ai/schemas/tool_calls.py), not on any
SDK's response type, so the same registry serves whichever provider `platform/ai/providers/` ends up calling.
"""

from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from ombuds.domain.errors import ToolExecutionError
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult

ToolHandler = Callable[[BaseModel], BaseModel]


class ToolRegistry:
    """Maps tool names to their schema and handler, so a provider turn can be dispatched without an if/elif chain."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """Register a tool's schema and the handler that executes validated arguments."""
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def definitions(self) -> list[ToolDefinition]:
        """All registered tool definitions, for building a provider request's tool list."""
        return list(self._definitions.values())

    def dispatch(self, call: ToolCall) -> ToolResult:
        """Validate `call.arguments` against the tool's schema, run its handler, and wrap the outcome.

        An unknown tool name, an argument-validation failure, or a handler raising `ToolExecutionError`
        each become an error `ToolResult` instead of an exception, so one bad call in a turn can't abort
        the rest of that turn's tool calls. Any other exception a handler raises is a bug, not an expected
        failure, and propagates unchanged instead of being reported as a tool error.
        """
        definition = self._definitions.get(call.name)
        if definition is None:
            return ToolResult(call_id=call.id, name=call.name, content=f"unknown tool: {call.name}", is_error=True)

        try:
            args = definition.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(call_id=call.id, name=call.name, content=str(exc), is_error=True)

        handler = self._handlers[call.name]
        try:
            result = handler(args)
        except ToolExecutionError as exc:
            return ToolResult(call_id=call.id, name=call.name, content=str(exc), is_error=True)
        return ToolResult(call_id=call.id, name=call.name, content=result.model_dump_json())

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Dispatch every tool call from one provider turn, in order."""
        return [self.dispatch(call) for call in calls]
