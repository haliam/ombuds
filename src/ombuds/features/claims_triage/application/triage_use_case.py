"""Orchestrates the end-to-end triage flow: a raw tool-use loop against Anthropic, no agent framework."""

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from ombuds.config import load_prompt
from ombuds.features.claims_triage.application.decision import TriageDecision, verify_decision
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.providers.base import LLMProvider
from ombuds.platform.ai.providers.fallback import build_default_provider
from ombuds.platform.ai.schemas.structured_output import StructuredOutputError, parse_structured_output
from ombuds.platform.ai.schemas.tool_calls import ToolResult
from ombuds.platform.ai.streaming import StreamEvent, ToolResultEvent, TurnDone

MAX_TOOL_TURNS = 8
MAX_REPAIR_ATTEMPTS = 2


class TriageResult(BaseModel):
    """Outcome of running the triage loop over one claim: the model's final answer plus every tool call made.

    `decision` is the validated, `check_eligibility`-verified `TriageDecision` when the model's final reply
    was a JSON verdict, or `None` when it instead asked the passenger a plain-text clarifying question
    (see prompt v4's "final answer format" — not every final turn is a decision).
    """

    model_config = ConfigDict(frozen=True)

    answer: str
    decision: TriageDecision | None
    tool_results: tuple[ToolResult, ...]


def _repair_message(error: StructuredOutputError) -> dict[str, object]:
    return {
        "role": "user",
        "content": f"Your reply didn't validate: {error}. Resend a corrected JSON object only, no other text.",
    }


def _parse_final_turn(text: str) -> TriageDecision | None:
    """Parse `text` as a `TriageDecision` if it looks like JSON, or `None` if it's a plain-text question.

    Raises `StructuredOutputError` when the model clearly attempted JSON (a `{` is present) but it doesn't
    parse or validate — that's the case callers should repair, as opposed to a legitimate plain-text reply.
    """
    if "{" not in text:
        return None
    return parse_structured_output(text, TriageDecision)


def run_triage(claim_text: str, *, provider: LLMProvider | None = None) -> TriageResult:
    """Run the tool-use loop for one claim: ask the model, dispatch any tool calls, repeat until it answers.

    Stops after `MAX_TOOL_TURNS` rounds even if the model keeps requesting tool calls, so a misbehaving
    model (or a stuck approval loop) can't spin forever against a live API.
    """
    provider = provider or build_default_provider()
    registry = build_tool_registry()
    system = load_prompt("claims_triage")
    messages: list[dict[str, object]] = [{"role": "user", "content": claim_text}]
    all_results: list[ToolResult] = []
    repair_attempts = 0

    for _ in range(MAX_TOOL_TURNS):
        turn = provider.run_turn(messages, registry.definitions(), system=system)
        messages.append({"role": "assistant", "content": turn.content})

        if not turn.tool_calls:
            try:
                decision = _parse_final_turn(turn.text)
                if decision is not None:
                    verify_decision(decision, all_results)
            except StructuredOutputError as exc:
                if repair_attempts >= MAX_REPAIR_ATTEMPTS:
                    raise
                repair_attempts += 1
                messages.append(_repair_message(exc))
                continue
            return TriageResult(answer=turn.text, decision=decision, tool_results=tuple(all_results))

        results = registry.dispatch_all(list(turn.tool_calls))
        all_results.extend(results)
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    for result in results
                ],
            }
        )

    raise RuntimeError(f"triage did not converge within {MAX_TOOL_TURNS} tool-use turns")


def stream_triage(claim_text: str, *, provider: LLMProvider | None = None) -> Iterator[StreamEvent]:
    """Like `run_triage`, but yield `StreamEvent`s as they happen instead of returning one final result.

    Yields every event a provider turn streams (text deltas, completed tool calls), plus a `ToolResultEvent`
    per dispatched tool call and each turn's `TurnDone`. Callers that need the final answer should watch for
    the last `TurnDone` with no `tool_calls`.
    """
    provider = provider or build_default_provider()
    registry = build_tool_registry()
    system = load_prompt("claims_triage")
    messages: list[dict[str, object]] = [{"role": "user", "content": claim_text}]

    for _ in range(MAX_TOOL_TURNS):
        turn_done: TurnDone | None = None
        for event in provider.stream_turn(messages, registry.definitions(), system=system):
            yield event
            if isinstance(event, TurnDone):
                turn_done = event

        assert turn_done is not None, "provider.stream_turn must end with a TurnDone"
        messages.append({"role": "assistant", "content": turn_done.content})

        if not turn_done.tool_calls:
            return

        results = registry.dispatch_all(list(turn_done.tool_calls))
        for result in results:
            yield ToolResultEvent(result=result)
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    for result in results
                ],
            }
        )

    raise RuntimeError(f"triage did not converge within {MAX_TOOL_TURNS} tool-use turns")
