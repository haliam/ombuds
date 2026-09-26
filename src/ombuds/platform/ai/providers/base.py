"""Provider-agnostic contract for one LLM turn: send a conversation and tool list, get an assistant turn back."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition


class ProviderTurn(BaseModel):
    """One assistant turn: any text, any requested tool calls, and the raw content to replay back as history.

    `content` is provider-specific (Anthropic content blocks, OpenAI message deltas, ...) and is only ever
    fed back to that same provider's next call — callers must not interpret it themselves.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: str
    content: object


class LLMProvider(Protocol):
    """A provider that can run one turn of a tool-use conversation."""

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        """Send `messages` (provider-native wire format) plus `tools` and `system`, and return the assistant turn."""
        ...
