"""Orchestrates the end-to-end triage flow: a raw tool-use loop against Anthropic, no agent framework."""

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from ombuds.config import load_prompt
from ombuds.features.claims_triage.tools.check_eligibility import CHECK_ELIGIBILITY_TOOL, check_eligibility
from ombuds.features.claims_triage.tools.log_claim import LOG_CLAIM_TOOL, LogClaimArgs, log_claim
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.platform.ai.providers.anthropic import AnthropicProvider
from ombuds.platform.ai.providers.base import LLMProvider
from ombuds.platform.ai.schemas.tool_calls import ToolResult
from ombuds.platform.ai.streaming import StreamEvent, ToolResultEvent, TurnDone
from ombuds.platform.ai.tool_loop import ToolRegistry

MAX_TOOL_TURNS = 8


class TriageResult(BaseModel):
    """Outcome of running the triage loop over one claim: the model's final answer plus every tool call made."""

    model_config = ConfigDict(frozen=True)

    answer: str
    tool_results: tuple[ToolResult, ...]


def _check_eligibility(args: BaseModel) -> BaseModel:
    assert isinstance(args, FlightDisruption)
    return check_eligibility(args)


def _log_claim(args: BaseModel) -> BaseModel:
    assert isinstance(args, LogClaimArgs)
    return log_claim(args)


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CHECK_ELIGIBILITY_TOOL, _check_eligibility)
    registry.register(LOG_CLAIM_TOOL, _log_claim)
    return registry


def run_triage(claim_text: str, *, provider: LLMProvider | None = None) -> TriageResult:
    """Run the tool-use loop for one claim: ask the model, dispatch any tool calls, repeat until it answers.

    Stops after `MAX_TOOL_TURNS` rounds even if the model keeps requesting tool calls, so a misbehaving
    model (or a stuck approval loop) can't spin forever against a live API.
    """
    provider = provider or AnthropicProvider()
    registry = _build_registry()
    system = load_prompt("claims_triage")
    messages: list[dict[str, object]] = [{"role": "user", "content": claim_text}]
    all_results: list[ToolResult] = []

    for _ in range(MAX_TOOL_TURNS):
        turn = provider.run_turn(messages, registry.definitions(), system=system)
        messages.append({"role": "assistant", "content": turn.content})

        if not turn.tool_calls:
            return TriageResult(answer=turn.text, tool_results=tuple(all_results))

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
    provider = provider or AnthropicProvider()
    registry = _build_registry()
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
