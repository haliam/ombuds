"""Anthropic provider: raw `anthropic` SDK tool-use turns. No agent framework — see ADR-0001 for where one lands."""

from collections.abc import Iterator

import anthropic

from ombuds.platform.ai.providers.base import ProviderTurn, ProviderUnavailableError
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.streaming import JSONBuffer, StreamEvent, TextDelta, ToolCallDelta, TurnDone

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
MAX_TOKENS = 1024

# Anthropic SDK exceptions that mean "this model is unavailable right now", once the SDK client's own
# retries (see AnthropicProvider.__init__) are already exhausted — connection failures/timeouts, rate
# limits, and 5xx-family status errors. Anything else (a 4xx from malformed input, an unexpected bug)
# is deliberately left uncaught, so it propagates instead of being retried or failed over pointlessly.
# See ADR-0006.
_RETRYABLE_ANTHROPIC_ERRORS = (
    anthropic.APIConnectionError,  # also covers APITimeoutError, a subclass
    anthropic.RateLimitError,
    anthropic.ConflictError,
    anthropic.ServiceUnavailableError,
    anthropic.OverloadedError,
    anthropic.DeadlineExceededError,
    anthropic.InternalServerError,
)


class AnthropicProvider:
    """Thin wrapper over the `anthropic` SDK's `messages.create`/`messages.stream`.

    Retries and timeouts are delegated to the SDK's own client (exponential backoff on connection errors,
    429s and 5xxs). Once those are exhausted, a still-retryable failure is translated into
    `ProviderUnavailableError` at this boundary; see `FallbackProvider` for the layer above that
    switches models on that error, and ADR-0006 for why resilience is split this way.
    """

    def __init__(
        self,
        model: str,
        client: anthropic.Anthropic | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._client = client or anthropic.Anthropic(timeout=timeout, max_retries=max_retries)
        self._model = model

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        """Send one turn to Anthropic and parse its response into a provider-agnostic `ProviderTurn`.

        Raises `ProviderUnavailableError` once the SDK's own retries are exhausted for a retryable
        failure (connection/timeout, rate limit, 5xx); any other exception propagates unchanged.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                tools=[_to_anthropic_tool(tool) for tool in tools],  # type: ignore[misc]
            )
        except _RETRYABLE_ANTHROPIC_ERRORS as exc:
            raise ProviderUnavailableError(str(exc)) from exc

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

    def stream_turn(
        self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        """Stream one turn: text deltas and completed tool calls as they arrive, ending with a `TurnDone`.

        Tool-call arguments arrive as fragments of partial JSON (Anthropic's `input_json_delta`), which
        `JSONBuffer` accumulates per call id and parses once that block closes. The final `TurnDone` is
        built from `get_final_message()` rather than the accumulated deltas, so it matches `run_turn`'s
        output exactly regardless of how the stream was chunked.

        Raises `ProviderUnavailableError` once the SDK's own retries are exhausted for a retryable
        failure; any other exception propagates unchanged. See `run_turn`.
        """
        buffer = JSONBuffer()
        block_ids: dict[int, str] = {}
        block_names: dict[int, str] = {}

        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                tools=[_to_anthropic_tool(tool) for tool in tools],  # type: ignore[misc]
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start" and event.content_block.type == "tool_use":
                        block_ids[event.index] = event.content_block.id
                        block_names[event.index] = event.content_block.name
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield TextDelta(text=event.delta.text)
                        elif event.delta.type == "input_json_delta":
                            buffer.append(block_ids[event.index], event.delta.partial_json)
                    elif event.type == "content_block_stop" and event.index in block_ids:
                        call_id = block_ids[event.index]
                        args = buffer.finalize(call_id)
                        yield ToolCallDelta(call=ToolCall(id=call_id, name=block_names[event.index], arguments=args))

                final = stream.get_final_message()
        except _RETRYABLE_ANTHROPIC_ERRORS as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        text = "".join(block.text for block in final.content if block.type == "text")
        tool_calls = tuple(
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            for block in final.content
            if block.type == "tool_use"
        )
        yield TurnDone(
            text=text,
            tool_calls=tool_calls,
            stop_reason=final.stop_reason or "",
            content=[block.model_dump() for block in final.content],
        )


def _to_anthropic_tool(tool: ToolDefinition) -> dict[str, object]:
    """Anthropic's tool-use wire format: name, description, and a JSON Schema for the arguments."""
    return {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema()}
