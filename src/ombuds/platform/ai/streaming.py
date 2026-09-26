"""Streaming primitives: provider-agnostic stream events, and a buffer for incrementally-arriving tool JSON.

A streaming provider turn arrives as a sequence of small deltas (text tokens, partial tool-input JSON
fragments) rather than one complete response. `StreamEvent` is what those deltas are normalized to;
`JSONBuffer` accumulates one tool call's fragments until they form a complete JSON object.
"""

import json

from pydantic import BaseModel, ConfigDict

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolResult


class TextDelta(BaseModel):
    """One incremental chunk of the assistant's text answer."""

    model_config = ConfigDict(frozen=True)

    text: str


class ToolCallDelta(BaseModel):
    """A tool call whose argument JSON has fully arrived and been parsed."""

    model_config = ConfigDict(frozen=True)

    call: ToolCall


class ToolResultEvent(BaseModel):
    """The outcome of dispatching one tool call, emitted as soon as it's available."""

    model_config = ConfigDict(frozen=True)

    result: ToolResult


class TurnDone(BaseModel):
    """Marks the end of one provider turn: the same information `ProviderTurn` carries, streamed last."""

    model_config = ConfigDict(frozen=True)

    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: str
    content: object


StreamEvent = TextDelta | ToolCallDelta | ToolResultEvent | TurnDone


class JSONBuffer:
    """Accumulates a tool call's argument JSON as it arrives in fragments, keyed by call id.

    Providers stream a tool call's input as partial JSON text rather than as one atomic value, so a
    call's arguments aren't parseable until its last fragment has arrived and `finalize` is called.
    """

    def __init__(self) -> None:
        self._fragments: dict[str, list[str]] = {}

    def append(self, call_id: str, fragment: str) -> None:
        """Append one JSON text fragment for `call_id`."""
        self._fragments.setdefault(call_id, []).append(fragment)

    def finalize(self, call_id: str) -> dict[str, object]:
        """Parse and discard the accumulated fragments for `call_id`.

        Raises `json.JSONDecodeError` if the accumulated text isn't valid JSON, and `ValueError` if it
        parses to something other than a JSON object. Callers should only call this once a provider has
        signalled that call's input is complete.
        """
        raw = "".join(self._fragments.pop(call_id, []))
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"tool call {call_id} arguments did not parse to a JSON object: {raw!r}")
        return parsed
