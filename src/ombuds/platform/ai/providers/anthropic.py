"""Anthropic provider: raw `anthropic` SDK tool-use turns. No agent framework — see ADR-0001 for where one lands."""

import hashlib
import json
from collections.abc import Iterator

import anthropic

from ombuds.platform.ai.providers.base import ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.streaming import JSONBuffer, StreamEvent, TextDelta, ToolCallDelta, TurnDone

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
MAX_TOKENS = 1024


def _idempotency_key(model: str, system: str, messages: list[dict[str, object]], tools: list[ToolDefinition]) -> str:
    """A stable key for this exact request, so a retried/re-sent call dedupes server-side instead of re-running.

    Anthropic's Messages API honors an `idempotency-key` header the same way Stripe's does. Deriving it from
    the request body (rather than a random uuid per call) means the SDK's own internal retries *and* a
    `FallbackProvider` retry against this same model reuse the same key — only a genuinely different request
    (a new turn, once the conversation history has grown) gets a new one.
    """
    payload = json.dumps(
        {"model": model, "system": system, "messages": messages, "tools": [tool.name for tool in tools]},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class AnthropicProvider:
    """Thin wrapper over the `anthropic` SDK's `messages.create`/`messages.stream`.

    Retries and timeouts are delegated to the SDK's own client (exponential backoff on connection errors,
    429s and 5xxs); see `FallbackProvider` for the layer above that switches models once those are exhausted.
    """

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._client = client or anthropic.Anthropic(timeout=timeout, max_retries=max_retries)
        self._model = model

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        """Send one turn to Anthropic and parse its response into a provider-agnostic `ProviderTurn`."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,  # type: ignore[arg-type]
            tools=[_to_anthropic_tool(tool) for tool in tools],  # type: ignore[misc]
            extra_headers={"idempotency-key": _idempotency_key(self._model, system, messages, tools)},
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

    def stream_turn(
        self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        """Stream one turn: text deltas and completed tool calls as they arrive, ending with a `TurnDone`.

        Tool-call arguments arrive as fragments of partial JSON (Anthropic's `input_json_delta`), which
        `JSONBuffer` accumulates per call id and parses once that block closes. The final `TurnDone` is
        built from `get_final_message()` rather than the accumulated deltas, so it matches `run_turn`'s
        output exactly regardless of how the stream was chunked.
        """
        buffer = JSONBuffer()
        block_ids: dict[int, str] = {}
        block_names: dict[int, str] = {}

        with self._client.messages.stream(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,  # type: ignore[arg-type]
            tools=[_to_anthropic_tool(tool) for tool in tools],  # type: ignore[misc]
            extra_headers={"idempotency-key": _idempotency_key(self._model, system, messages, tools)},
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
