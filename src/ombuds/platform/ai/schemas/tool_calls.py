"""Tool-call schemas: the provider-agnostic shape of a tool definition, a requested call, and its result."""

from pydantic import BaseModel, ConfigDict


class ToolDefinition(BaseModel):
    """Describes one callable tool: name, description, and the model its arguments must validate against."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    description: str
    args_model: type[BaseModel]
    raw_schema: dict[str, object] | None = None

    def input_schema(self) -> dict[str, object]:
        """JSON Schema for the tool's arguments, in the shape both Anthropic and OpenAI tool-use APIs expect.

        Derived from `args_model` normally. A definition built from an MCP `list_tools` response
        (`platform/mcp/client.py`) has no local `args_model` to derive a schema from — validation
        happens on the far side of the MCP call instead — so it sets `raw_schema` to the schema the
        server already sent, and that's returned as-is.
        """
        if self.raw_schema is not None:
            return self.raw_schema
        return self.args_model.model_json_schema()


class ToolCall(BaseModel):
    """One tool invocation an LLM requested, with arguments not yet validated against the tool's schema."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, object]


class ToolResult(BaseModel):
    """Outcome of executing one `ToolCall`, ready to feed back to the LLM as the next turn's tool-result message."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    name: str
    content: str
    is_error: bool = False
