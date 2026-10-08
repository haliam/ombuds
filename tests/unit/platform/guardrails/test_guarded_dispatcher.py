from collections.abc import Sequence

from pydantic import BaseModel

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult
from ombuds.platform.guardrails.guarded_dispatcher import GuardedDispatcher


class _Args(BaseModel):
    query: str


_DEFINITION = ToolDefinition(name="search_kb", description="d", args_model=_Args)


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.received: list[ToolCall] = []

    def definitions(self) -> Sequence[ToolDefinition]:
        return [_DEFINITION]

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        self.received.extend(calls)
        return [ToolResult(call_id=call.id, name=call.name, content="ok") for call in calls]


def test_arguments_are_redacted_before_reaching_the_inner_dispatcher() -> None:
    inner = _RecordingDispatcher()
    call = ToolCall(id="1", name="search_kb", arguments={"query": "refund for jane@example.com"})

    results = GuardedDispatcher(inner).dispatch_all([call])

    assert inner.received == [call.model_copy(update={"arguments": {"query": "refund for [EMAIL]"}})]
    assert results == [ToolResult(call_id="1", name="search_kb", content="ok")]


def test_definitions_pass_through_unchanged() -> None:
    assert GuardedDispatcher(_RecordingDispatcher()).definitions() == [_DEFINITION]
