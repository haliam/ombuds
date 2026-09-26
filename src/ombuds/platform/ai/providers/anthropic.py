"""Anthropic provider: raw `anthropic` SDK tool-use turns. No agent framework — see ADR-0001 for where one lands."""

import anthropic

from ombuds.platform.ai.providers.base import ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 1024


class AnthropicProvider:
    """Thin wrapper over `anthropic.Anthropic().messages.create`. No retries, streaming, or fallback yet."""

    def __init__(self, client: anthropic.Anthropic | None = None, model: str = DEFAULT_MODEL) -> None:
        self._client = client or anthropic.Anthropic()
        self._model = model

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        """Send one turn to Anthropic and parse its response into a provider-agnostic `ProviderTurn`."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,  # type: ignore[arg-type]
            tools=[_to_anthropic_tool(tool) for tool in tools],  # type: ignore[misc]
        )

        text = "".join(block.text for block in response.content if block.type == "text")
        tool_calls = tuple(
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        )

        return ProviderTurn(
            text=text,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "",
            content=[block.model_dump() for block in response.content],
        )


def _to_anthropic_tool(tool: ToolDefinition) -> dict[str, object]:
    """Anthropic's tool-use wire format: name, description, and a JSON Schema for the arguments."""
    return {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema()}
