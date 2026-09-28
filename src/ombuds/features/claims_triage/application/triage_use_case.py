"""Orchestrates the end-to-end triage flow: `run_triage` drives a LangGraph tool-calling loop
(`agent/graph.py`) against a provider; `stream_triage` still runs the raw streaming loop directly,
since streaming events aren't yet threaded through the graph.
"""

import uuid
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from ombuds.config import load_prompt
from ombuds.features.claims_triage.agent.graph import (
    MAX_REPAIR_ATTEMPTS,
    MAX_TOOL_TURNS,
    build_triage_graph,
    tool_result_message,
)
from ombuds.features.claims_triage.agent.memory.long_term import LongTermMemory, LongTermMemoryStore
from ombuds.features.claims_triage.agent.memory.short_term import ShortTermMemory
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.features.claims_triage.tools import build_tool_registry, scope_for_agent
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

    `claim_id` is the server-issued id every claim-scoped tool call in this run was bound to (ADR-0009).

    `escalated` is `True` when the run ended via `agent/nodes/escalate_retry.py` instead of a verified
    decision or a clarifying question — the loop couldn't converge, couldn't produce a decision that
    passed repair/verification, or hit a stop_reason it can't recover from. `escalation_reason` then
    holds a human-readable explanation; `decision` is `None` and `answer` is the best text available.
    """

    model_config = ConfigDict(frozen=True)

    claim_id: str
    answer: str
    decision: TriageDecision | None
    tool_results: tuple[ToolResult, ...]
    escalated: bool = False
    escalation_reason: str | None = None


def run_triage(
    claim_text: str,
    *,
    claim_id: str | None = None,
    provider: LLMProvider | None = None,
    use_mcp: bool = False,
    claimant_id: str | None = None,
    long_term_store: LongTermMemoryStore | None = None,
) -> TriageResult:
    """Run the tool-use loop for one claim: ask the model, dispatch any tool calls, repeat until it answers.

    Delegates to the LangGraph graph built by `agent/graph.py`, which stops after `MAX_TOOL_TURNS` rounds
    even if the model keeps requesting tool calls, so a misbehaving model (or a stuck approval loop) can't
    spin forever against a live API. A run that can't converge, or can't produce a decision that survives
    repair/verification, comes back as `TriageResult.escalated=True` rather than raising — see
    `agent/nodes/escalate_retry.py`.

    `use_mcp=True` dispatches tool calls over a real MCP session (`platform/mcp/client.py`), spawning the
    standalone server (`platform/mcp/server.py`) as a subprocess, instead of the default in-process
    `ToolRegistry`. The graph itself doesn't know the difference — both satisfy `ToolDispatcher`.

    `claim_id` identifies the claim this run acts on; a new one is issued when omitted. The model never
    chooses it: any `claim_id` it passes to `log_claim` is replaced with this one, and the model is only
    offered the agent's tool set — never `issue_payment` (`tools.scope_for_agent`, ADR-0009).

    `claimant_id` + `long_term_store` opt into cross-run memory (`agent/memory/long_term.py`): when both
    are given, prior facts about this claimant are shown to the model as a context block in the first user
    turn, and a run that ends with a verified decision consolidates its rules-derived `ShortTermMemory`
    facts back into the store. Omit either and there is no cross-run recall.
    """
    claim_id = claim_id or str(uuid.uuid4())
    provider = provider or build_default_provider()
    system = load_prompt("claims_triage")
    long_term = long_term_store.load(claimant_id) if claimant_id and long_term_store else LongTermMemory()

    if use_mcp:
        with McpToolClient() as mcp_client:
            result, long_term = _invoke_graph(
                provider, scope_for_agent(mcp_client, claim_id), claim_id, system, claim_text, long_term
            )
    else:
        result, long_term = _invoke_graph(
            provider, scope_for_agent(build_tool_registry(), claim_id), claim_id, system, claim_text, long_term
        )

    if claimant_id and long_term_store:
        long_term_store.save(claimant_id, long_term)
    return result


def _invoke_graph(
    provider: LLMProvider,
    registry: ToolDispatcher,
    claim_id: str,
    system: str,
    claim_text: str,
    long_term: LongTermMemory,
) -> tuple[TriageResult, LongTermMemory]:
    app = build_triage_graph(provider, registry, system)

    final_state = app.invoke(
        {
            "messages": [_first_user_message(claim_text, long_term)],
            "tool_results": [],
            "pending_tool_calls": (),
            "text": "",
            "turns": 0,
            "repair_attempts": 0,
            "answer": None,
            "decision": None,
            "done": False,
            "short_term": ShortTermMemory(),
            "stop_reason": "",
            "escalated": False,
            "escalation_reason": None,
        },
        config={"recursion_limit": 4 * MAX_TOOL_TURNS + 2 * MAX_REPAIR_ATTEMPTS + 10},
    )
    result = TriageResult(
        claim_id=claim_id,
        answer=final_state["answer"],
        decision=final_state["decision"],
        tool_results=tuple(final_state["tool_results"]),
        escalated=final_state["escalated"],
        escalation_reason=final_state["escalation_reason"],
    )
    updated_long_term = long_term
    if final_state["decision"] is not None:
        for key, value in final_state["short_term"].facts.items():
            updated_long_term = updated_long_term.remember(f"last_{key}", value)
    return result, updated_long_term


def _first_user_message(claim_text: str, long_term: LongTermMemory) -> dict[str, object]:
    """The claim as the opening user turn, preceded by any cross-run facts as a separate context block.

    Memory goes here rather than in the system prompt so nothing a past run stored is ever promoted to
    system-level trust, and the system prompt stays the constant versioned prompt (W2 review F-06).
    """
    context = long_term.as_context()
    if context is None:
        return {"role": "user", "content": claim_text}
    return {
        "role": "user",
        "content": [{"type": "text", "text": context}, {"type": "text", "text": claim_text}],
    }


def stream_triage(claim_text: str, *, provider: LLMProvider | None = None) -> Iterator[StreamEvent]:
    """Like `run_triage`, but yield `StreamEvent`s as they happen instead of returning one final result.

    Yields every event a provider turn streams (text deltas, completed tool calls), plus a `ToolResultEvent`
    per dispatched tool call and each turn's `TurnDone`. Callers that need the final answer should watch for
    the last `TurnDone` with no `tool_calls`.
    """
    provider = provider or build_default_provider()
    registry = scope_for_agent(build_tool_registry(), str(uuid.uuid4()))
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
