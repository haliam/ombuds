"""Provider-agnostic contract for one LLM turn: send a conversation and tool list, get an assistant turn back."""

from collections.abc import Iterator, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent


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


class ProviderUnavailableError(Exception):
    """Raised by an `LLMProvider` adapter when the provider itself is unavailable, not merely erroring.

    Each adapter translates its own SDK's retryable-but-now-exhausted failures (a connection drop, a
    timeout, a rate limit, a 5xx) into this one provider-agnostic type at its own boundary — see
    `AnthropicProvider` and ADR-0006. `FallbackProvider` catches only this type to decide when to retry
    or fail over to a different model; anything else (a 4xx from malformed input, a bug in our own
    response parsing) propagates unchanged instead of triggering a pointless retry or fallover.
    """


class LLMProvider(Protocol):
    """A provider that can run one turn of a tool-use conversation."""

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        """Send `messages` (provider-native wire format) plus `tools` and `system`, and return the assistant turn."""
        ...

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        """Like `run_turn`, but yield incremental `StreamEvent`s as they arrive, ending with a `TurnDone`."""
        ...
