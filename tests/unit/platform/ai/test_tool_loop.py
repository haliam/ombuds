import pytest
from pydantic import BaseModel, ConfigDict

from ombuds.domain.errors import ToolExecutionError
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.tool_loop import ToolRegistry


class _EchoArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str


class _EchoResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    echoed: str


def _echo(args: BaseModel) -> BaseModel:
    assert isinstance(args, _EchoArgs)
    return _EchoResult(echoed=args.message)


def _failing(args: BaseModel) -> BaseModel:
    raise ToolExecutionError("downstream dependency unavailable")


def _buggy(args: BaseModel) -> BaseModel:
    raise RuntimeError("not an expected tool failure")


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="echo", description="Echoes its input.", args_model=_EchoArgs), _echo)
    registry.register(ToolDefinition(name="failing", description="Always fails.", args_model=_EchoArgs), _failing)
    registry.register(ToolDefinition(name="buggy", description="Always bugs out.", args_model=_EchoArgs), _buggy)
    return registry


def test_dispatch_validates_and_runs_the_handler() -> None:
    registry = _registry()
    call = ToolCall(id="call-1", name="echo", arguments={"message": "hi"})

    result = registry.dispatch(call)

    assert result.call_id == "call-1"
    assert result.is_error is False
    assert result.content == '{"echoed":"hi"}'


def test_dispatch_reports_unknown_tool_as_an_error_result() -> None:
    registry = _registry()
    call = ToolCall(id="call-2", name="nonexistent", arguments={})

    result = registry.dispatch(call)

    assert result.is_error is True
    assert "unknown tool" in result.content


def test_dispatch_reports_invalid_arguments_as_an_error_result() -> None:
    registry = _registry()
    call = ToolCall(id="call-3", name="echo", arguments={"message": 123})

    result = registry.dispatch(call)

    assert result.is_error is True


def test_dispatch_all_preserves_call_order() -> None:
    registry = _registry()
    calls = [
        ToolCall(id="a", name="echo", arguments={"message": "first"}),
        ToolCall(id="b", name="echo", arguments={"message": "second"}),
    ]

    results = registry.dispatch_all(calls)

    assert [r.call_id for r in results] == ["a", "b"]


def test_dispatch_all_does_not_abort_after_a_failing_call() -> None:
    registry = _registry()
    calls = [
        ToolCall(id="a", name="nonexistent", arguments={}),
        ToolCall(id="b", name="echo", arguments={"message": "second"}),
    ]

    results = registry.dispatch_all(calls)

    assert results[0].is_error is True
    assert results[1].is_error is False
    assert results[1].content == '{"echoed":"second"}'


def test_definitions_returns_every_registered_tool() -> None:
    registry = _registry()

    definitions = registry.definitions()

    assert [d.name for d in definitions] == ["echo", "failing", "buggy"]


def test_dispatch_reports_a_tool_execution_error_as_an_error_result() -> None:
    registry = _registry()
    call = ToolCall(id="call-4", name="failing", arguments={"message": "hi"})

    result = registry.dispatch(call)

    assert result.is_error is True
    assert result.content == "downstream dependency unavailable"


def test_dispatch_propagates_an_unexpected_handler_exception() -> None:
    """A bug in a handler is not an expected tool failure — it must not be swallowed as an error result."""
    registry = _registry()
    call = ToolCall(id="call-5", name="buggy", arguments={"message": "hi"})

    with pytest.raises(RuntimeError, match="not an expected tool failure"):
        registry.dispatch(call)
