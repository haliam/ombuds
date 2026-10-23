"""Orchestrates the end-to-end triage flow over the LangGraph tool-calling loop (`agent/graph.py`).

`run_triage` returns one `TriageResult`; `stream_triage` runs the *same* graph and yields progress events
followed by the same `TriageResult`, so both endpoints share one verification/repair/escalation path
(W2 review F-07).
"""

import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, ConfigDict

from ombuds.config import load_prompt
from ombuds.features.claims_triage.agent.graph import (
    MAX_REPAIR_ATTEMPTS,
    MAX_TOOL_TURNS,
    build_triage_graph,
)
from ombuds.features.claims_triage.agent.memory.long_term import LongTermMemory, LongTermMemoryStore
from ombuds.features.claims_triage.agent.memory.short_term import ShortTermMemory
from ombuds.features.claims_triage.agent.nodes.escalate_retry import ESCALATION_ANSWER
from ombuds.features.claims_triage.agent.state import AgentState
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.features.claims_triage.tools import scope_for_agent
from ombuds.platform.ai.providers.base import LLMProvider
from ombuds.platform.ai.providers.fallback import build_default_provider
from ombuds.platform.ai.schemas.tool_calls import ToolResult
from ombuds.platform.ai.streaming import ToolCallDelta, ToolResultEvent
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.audit_log import AuditEvent, AuditKind, AuditLog
from ombuds.platform.guardrails.guarded_dispatcher import GuardedDispatcher
from ombuds.platform.guardrails.injection_detection import InjectionResult, detect
from ombuds.platform.guardrails.pii_filter import redact, redact_value
from ombuds.platform.mcp.client import McpToolClient
from ombuds.platform.observability.tracing import start_span, trace_stream

__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "MAX_TOOL_TURNS",
    "TriageCompleted",
    "TriageResult",
    "TriageStreamEvent",
    "run_triage",
    "stream_triage",
]

_RECURSION_LIMIT = 4 * MAX_TOOL_TURNS + 2 * MAX_REPAIR_ATTEMPTS + 10
TRIAGE_SPAN = "triage.run"
INJECTION_SPAN = "triage.injection_escalation"

INJECTION_ESCALATION_REASON = "Possible prompt injection in the claim text; needs human review."


class TriageResult(BaseModel):
    """Outcome of running the triage loop over one claim: the model's final answer plus every tool call made.

    `decision` is the validated, `check_eligibility`-verified `TriageDecision` when the model's final reply
    was a JSON verdict, or `None` when it instead asked the passenger a plain-text clarifying question
    (see prompt v4's "final answer format" — not every final turn is a decision).

    `claim_id` is the server-issued id every claim-scoped tool call in this run was bound to (ADR-0009).

    `escalated` is `True` when the run ended via `agent/nodes/escalate_retry.py` instead of a verified
    decision or a clarifying question — the loop couldn't converge, couldn't produce a decision that
    passed repair/verification, or hit a stop_reason it can't recover from. `escalation_reason` then
    holds a human-readable explanation; `decision` is `None` and `answer` is a fixed human-review message.
    """

    model_config = ConfigDict(frozen=True)

    claim_id: str
    answer: str
    decision: TriageDecision | None
    tool_results: tuple[ToolResult, ...]
    escalated: bool = False
    escalation_reason: str | None = None


class TriageCompleted(BaseModel):
    """The last event `stream_triage` yields: the run's verified outcome, identical to `run_triage`'s result."""

    model_config = ConfigDict(frozen=True)

    result: TriageResult


TriageStreamEvent = ToolCallDelta | ToolResultEvent | TriageCompleted


def run_triage(
    claim_text: str,
    *,
    registry: ToolDispatcher,
    claim_id: str | None = None,
    provider: LLMProvider | None = None,
    use_mcp: bool = False,
    claimant_id: str | None = None,
    long_term_store: LongTermMemoryStore | None = None,
    audit: AuditLog | None = None,
) -> TriageResult:
    """Run the tool-use loop for one claim: ask the model, dispatch any tool calls, repeat until it answers.

    Delegates to the LangGraph graph built by `agent/graph.py`, which stops after `MAX_TOOL_TURNS` rounds
    even if the model keeps requesting tool calls, so a misbehaving model (or a stuck approval loop) can't
    spin forever against a live API. A run that can't converge, or can't produce a decision that survives
    repair/verification, comes back as `TriageResult.escalated=True` rather than raising — see
    `agent/nodes/escalate_retry.py`.

    `registry` is the full tool catalogue the composition root built (`application/runtime.py`), narrowed here
    to the agent's tools. With `use_mcp=True` it is unused: the server subprocess builds its own over the same
    Postgres.

    `use_mcp=True` dispatches tool calls over a real MCP session (`platform/mcp/client.py`), spawning the
    standalone server (`platform/mcp/server.py`) as a subprocess, instead of the default in-process
    `ToolRegistry`. The graph itself doesn't know the difference — both satisfy `ToolDispatcher`.

    Claim text that looks like a prompt injection (`platform/guardrails/injection_detection.py`) is escalated
    to a human before any model call or tool dispatch — see `_injection_escalation`.

    `claim_id` identifies the claim this run acts on; a new one is issued when omitted. The model never
    chooses it: any `claim_id` it passes to `log_claim` is replaced with this one, and the model is only
    offered the agent's tool set — never `issue_payment` (`tools.scope_for_agent`, ADR-0009).

    `claimant_id` + `long_term_store` opt into cross-run memory (`agent/memory/long_term.py`): when both
    are given, prior facts about this claimant are shown to the model as a context block in the first user
    turn, and a run that ends with a verified decision consolidates its rules-derived `ShortTermMemory`
    facts back into the store. Omit either and there is no cross-run recall.

    `audit` receives the two events no inner seam can see: an injection escalation and a call to a tool outside
    the agent's set (ADR-0016). Omit it and neither is recorded.
    """
    run = _prepare_run(claim_text, claim_id, provider, audit)
    if isinstance(run, TriageResult):
        return run
    long_term = long_term_store.load(claimant_id) if claimant_id and long_term_store else LongTermMemory()

    if use_mcp:
        with McpToolClient() as mcp_client:
            result, long_term = _invoke_graph(run, _agent_tools(mcp_client, run.claim_id, audit), long_term)
    else:
        result, long_term = _invoke_graph(run, _agent_tools(registry, run.claim_id, audit), long_term)

    if claimant_id and long_term_store:
        long_term_store.save(claimant_id, long_term)
    return result


@dataclass(frozen=True)
class _PreparedRun:
    """What `run_triage` and `stream_triage` share once a claim has passed the pre-model checks."""

    claim_id: str
    claim_text: str
    provider: LLMProvider
    system: str


def _prepare_run(
    claim_text: str, claim_id: str | None, provider: LLMProvider | None, audit: AuditLog | None
) -> _PreparedRun | TriageResult:
    """The setup both entry points run before the graph: issue the `claim_id`, screen for injection, redact PII.

    Returns the injection escalation instead when the claim text looks like an instruction to the model, so
    the caller returns it without ever building a provider or touching a tool. One place for both paths means
    one place to attach tracing or auditing to a run.
    """
    claim_id = claim_id or str(uuid.uuid4())
    injection = detect(claim_text)
    if injection.suspicious:
        with start_span(INJECTION_SPAN, claim_id=claim_id):
            if audit is not None:
                audit.record(_injection_event(claim_id, injection))
            return _injection_escalation(claim_id)
    return _PreparedRun(
        claim_id=claim_id,
        claim_text=redact(claim_text).text,
        provider=provider or build_default_provider(),
        system=load_prompt("claims_triage"),
    )


def _injection_event(claim_id: str, injection: InjectionResult) -> AuditEvent:
    """What was flagged, as counts per kind: the detector never reports the matched text (safe to store)."""
    return AuditEvent(
        kind=AuditKind.INJECTION_ESCALATION,
        subject="claim_text",
        outcome="escalated",
        claim_id=claim_id,
        detail={"findings": {finding.kind.value: finding.count for finding in injection.findings}},
    )


def _injection_escalation(claim_id: str) -> TriageResult:
    """The result for a claim that looks like an instruction to the model: it never reaches the model (ADR-0014).

    Shaped like every other escalation: the fixed human-review `answer`, with the specific cause in
    `escalation_reason`.
    """
    return TriageResult(
        claim_id=claim_id,
        answer=ESCALATION_ANSWER,
        decision=None,
        tool_results=(),
        escalated=True,
        escalation_reason=INJECTION_ESCALATION_REASON,
    )


def _agent_tools(dispatcher: ToolDispatcher, claim_id: str, audit: AuditLog | None) -> ToolDispatcher:
    """The agent's tools for one run: pinned to `claim_id` (ADR-0009), PII redacted from arguments (ADR-0013)."""
    return GuardedDispatcher(scope_for_agent(dispatcher, claim_id, audit))


def _invoke_graph(
    run: _PreparedRun, tools: ToolDispatcher, long_term: LongTermMemory
) -> tuple[TriageResult, LongTermMemory]:
    app = build_triage_graph(run.provider, tools, run.system)
    with start_span(TRIAGE_SPAN, claim_id=run.claim_id):
        final_state = cast(
            AgentState,
            app.invoke(_initial_state(run.claim_text, long_term), config={"recursion_limit": _RECURSION_LIMIT}),
        )
    return _to_result(run.claim_id, final_state), _consolidate(long_term, final_state)


def _initial_state(claim_text: str, long_term: LongTermMemory) -> AgentState:
    return {
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
    }


def _to_result(claim_id: str, final_state: AgentState) -> TriageResult:
    """Build the caller-facing result, redacting the model-authored free text in it (ADR-0013)."""
    decision: TriageDecision | None = final_state["decision"]
    if decision is not None:
        decision = decision.model_copy(update={"explanation": redact(decision.explanation).text})
    escalation_reason = final_state["escalation_reason"]
    return TriageResult(
        claim_id=claim_id,
        answer=redact(final_state["answer"] or "").text,
        decision=decision,
        tool_results=tuple(final_state["tool_results"]),
        escalated=final_state["escalated"],
        escalation_reason=None if escalation_reason is None else redact(escalation_reason).text,
    )


def _consolidate(long_term: LongTermMemory, final_state: AgentState) -> LongTermMemory:
    """Fold a run's rules-derived short-term facts into long-term memory, only when it reached a verified decision."""
    if final_state["decision"] is None:
        return long_term
    for key, value in final_state["short_term"].facts.items():
        long_term = long_term.remember(f"last_{key}", value)
    return long_term


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


def stream_triage(
    claim_text: str,
    *,
    registry: ToolDispatcher,
    claim_id: str | None = None,
    provider: LLMProvider | None = None,
    audit: AuditLog | None = None,
) -> Iterator[TriageStreamEvent]:
    """Run the same graph as `run_triage`, yielding progress events as they happen, then the final result.

    Yields a `ToolCallDelta` as each tool call the model requests completes and a `ToolResultEvent` as each
    tool returns, then exactly one `TriageCompleted` carrying the same verified `TriageResult` `run_triage`
    would return. Model text is never yielded on its own: until `finalize` has verified it, a reply may be a
    verdict the rules engine contradicts, so the only model-derived text a caller sees is the final result's.
    """
    run = _prepare_run(claim_text, claim_id, provider, audit)
    if isinstance(run, TriageResult):
        yield TriageCompleted(result=run)
        return
    app = build_triage_graph(run.provider, _agent_tools(registry, run.claim_id, audit), run.system, stream=True)

    final_state: AgentState | None = None
    graph_stream = app.stream(
        _initial_state(run.claim_text, LongTermMemory()),
        config={"recursion_limit": _RECURSION_LIMIT},
        stream_mode=["custom", "values"],
    )
    for mode, chunk in trace_stream(TRIAGE_SPAN, iter(graph_stream), claim_id=run.claim_id):
        if mode == "custom" and isinstance(chunk, ToolCallDelta | ToolResultEvent):
            yield _redact_event(chunk)
        elif mode == "values" and isinstance(chunk, Mapping):
            final_state = cast(AgentState, chunk)
    if final_state is None:
        raise RuntimeError("triage graph produced no state")
    yield TriageCompleted(result=_to_result(run.claim_id, final_state))


def _redact_event(event: ToolCallDelta | ToolResultEvent) -> ToolCallDelta | ToolResultEvent:
    """Redact the model-authored arguments of a streamed tool call; results come from our own tools."""
    if isinstance(event, ToolCallDelta):
        arguments = redact_value(event.call.arguments)
        assert isinstance(arguments, dict)
        return ToolCallDelta(call=event.call.model_copy(update={"arguments": arguments}))
    return event
