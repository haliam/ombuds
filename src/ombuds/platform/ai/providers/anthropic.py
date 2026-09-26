"""Anthropic provider: raw `anthropic` SDK tool-use turns. No agent framework — see ADR-0001 for where one lands."""

from collections.abc import Iterator

import anthropic

from ombuds.platform.ai.providers.base import ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition
from ombuds.platform.ai.streaming import JSONBuffer, StreamEvent, TextDelta, ToolCallDelta, TurnDone

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 1024


class AnthropicProvider:
    """Thin wrapper over the `anthropic` SDK's `messages.create`/`messages.stream`. No retries or fallback yet."""

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
