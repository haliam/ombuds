from pydantic import BaseModel, ConfigDict

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult


class _EchoArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str


def test_tool_definition_input_schema_reflects_args_model() -> None:
    definition = ToolDefinition(name="echo", description="Echoes its input.", args_model=_EchoArgs)

    schema = definition.input_schema()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    message_schema = properties["message"]
    assert isinstance(message_schema, dict)

    assert message_schema["type"] == "string"
    assert schema["required"] == ["message"]


def test_tool_call_is_frozen() -> None:
    call = ToolCall(id="call-1", name="echo", arguments={"message": "hi"})

    try:
        call.id = "call-2"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True

    assert raised


def test_tool_result_defaults_is_error_to_false() -> None:
    result = ToolResult(call_id="call-1", name="echo", content="ok")

    assert result.is_error is False
