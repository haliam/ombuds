"""Orchestrates the end-to-end triage flow: `run_triage` drives a LangGraph tool-calling loop
(`agent/graph.py`) against a provider; `stream_triage` still runs the raw streaming loop directly,
since streaming events aren't yet threaded through the graph.
"""

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from ombuds.config import load_prompt
from ombuds.features.claims_triage.agent.graph import (
    MAX_REPAIR_ATTEMPTS,
    MAX_TOOL_TURNS,
    build_triage_graph,
    tool_result_message,
)
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.providers.base import LLMProvider
from ombuds.platform.ai.providers.fallback import build_default_provider
from ombuds.platform.ai.schemas.tool_calls import ToolResult
from ombuds.platform.ai.streaming import StreamEvent, ToolResultEvent, TurnDone
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.mcp.client import McpToolClient

__all__ = ["MAX_REPAIR_ATTEMPTS", "MAX_TOOL_TURNS", "TriageResult", "run_triage", "stream_triage"]


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


def run_triage(claim_text: str, *, provider: LLMProvider | None = None, use_mcp: bool = False) -> TriageResult:
    """Run the tool-use loop for one claim: ask the model, dispatch any tool calls, repeat until it answers.

    Delegates to the LangGraph graph built by `agent/graph.py`, which stops after `MAX_TOOL_TURNS` rounds
    even if the model keeps requesting tool calls, so a misbehaving model (or a stuck approval loop) can't
    spin forever against a live API.

    `use_mcp=True` dispatches tool calls over a real MCP session (`platform/mcp/client.py`), spawning the
    standalone server (`platform/mcp/server.py`) as a subprocess, instead of the default in-process
    `ToolRegistry`. The graph itself doesn't know the difference — both satisfy `ToolDispatcher`.
    """
    provider = provider or build_default_provider()
    system = load_prompt("claims_triage")

    if use_mcp:
        with McpToolClient() as registry:
            return _invoke_graph(provider, registry, system, claim_text)
    return _invoke_graph(provider, build_tool_registry(), system, claim_text)


def _invoke_graph(provider: LLMProvider, registry: ToolDispatcher, system: str, claim_text: str) -> TriageResult:
    app = build_triage_graph(provider, registry, system)

    final_state = app.invoke(
        {
            "messages": [{"role": "user", "content": claim_text}],
            "tool_results": [],
            "pending_tool_calls": (),
            "text": "",
            "turns": 0,
            "repair_attempts": 0,
            "answer": None,
            "decision": None,
            "done": False,
        },
        config={"recursion_limit": 4 * MAX_TOOL_TURNS + 2 * MAX_REPAIR_ATTEMPTS + 10},
    )
    return TriageResult(
        answer=final_state["answer"],
        decision=final_state["decision"],
        tool_results=tuple(final_state["tool_results"]),
    )


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
        messages.append(tool_result_message(results))

    raise RuntimeError(f"triage did not converge within {MAX_TOOL_TURNS} tool-use turns")
