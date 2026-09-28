"""LangGraph tool-calling loop: model turn -> dispatch tool calls -> repeat until a final answer.

Replaces the hand-rolled `for` loop `application/triage_use_case.py` used in W1. The graph structure is
the same loop, just expressed as nodes and conditional edges: `call_model` -> (tool calls present?)
`dispatch_tools` -> back to `call_model`; or (no tool calls) `finalize`, which either returns the answer
or, on a validation/verification failure, loops back to `call_model` with a repair message. A run that
can't converge or can't produce a verified decision within budget routes to `escalate`
(`agent/nodes/escalate_retry.py`) instead of raising — see that module's docstring.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ombuds.features.claims_triage.agent.nodes.escalate_retry import UNRECOVERABLE_STOP_REASONS, escalate
from ombuds.features.claims_triage.agent.state import AgentState
from ombuds.features.claims_triage.application.decision import TriageDecision, verify_decision
from ombuds.platform.ai.providers.base import LLMProvider
from ombuds.platform.ai.schemas.structured_output import StructuredOutputError, parse_structured_output
from ombuds.platform.ai.schemas.tool_calls import ToolResult
from ombuds.platform.ai.tool_loop import ToolDispatcher

MAX_TOOL_TURNS = 8
MAX_REPAIR_ATTEMPTS = 2


def tool_result_message(results: list[ToolResult]) -> dict[str, object]:
    """Build the wire-format user message that replays a batch of tool results back to the model."""
    return {
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


def _repair_message(error: StructuredOutputError) -> dict[str, object]:
    return {
        "role": "user",
        "content": f"Your reply didn't validate: {error}. Resend a corrected JSON object only, no other text.",
    }


def _augmented_system(system: str, state: AgentState) -> str:
    """`system` plus whatever `short_term`/`long_term` memory has to say, as extra context blocks."""
    blocks = [system, state["long_term"].as_context(), state["short_term"].as_context()]
    return "\n\n".join(block for block in blocks if block)


def _parse_final_turn(text: str) -> TriageDecision | None:
    """Parse `text` as a `TriageDecision` if it looks like JSON, or `None` for a plain-text reply.

    Raises `StructuredOutputError` when the model attempted JSON (a `{` is present) but it doesn't
    parse or validate — see `application/triage_use_case.py`'s original docstring for why that's the
    case callers should repair rather than a legitimate plain-text question.
    """
    if "{" not in text:
        return None
    return parse_structured_output(text, TriageDecision)


def build_triage_graph(provider: LLMProvider, registry: ToolDispatcher, system: str) -> CompiledStateGraph[AgentState]:
    """Compile the tool-calling loop graph, bound to one provider, tool registry, and system prompt."""

    def call_model(state: AgentState) -> dict[str, object]:
        turns = state["turns"] + 1
        if turns > MAX_TOOL_TURNS:
            return {
                "turns": turns,
                "escalation_reason": f"did not converge within {MAX_TOOL_TURNS} tool-use turns",
            }
        turn = provider.run_turn(state["messages"], registry.definitions(), system=_augmented_system(system, state))
        messages = [*state["messages"], {"role": "assistant", "content": turn.content}]
        escalation_reason = (
            f"model turn ended with stop_reason={turn.stop_reason!r}"
            if turn.stop_reason in UNRECOVERABLE_STOP_REASONS
            else None
        )
        return {
            "messages": messages,
            "pending_tool_calls": turn.tool_calls,
            "text": turn.text,
            "turns": turns,
            "stop_reason": turn.stop_reason,
            "escalation_reason": escalation_reason,
        }

    def route_after_model(state: AgentState) -> str:
        if state["escalation_reason"]:
            return "escalate"
        return "dispatch_tools" if state["pending_tool_calls"] else "finalize"

    def dispatch_tools(state: AgentState) -> dict[str, object]:
        results = registry.dispatch_all(list(state["pending_tool_calls"]))
        messages = [*state["messages"], tool_result_message(results)]
        short_term = state["short_term"]
        for result in results:
            if not result.is_error:
                short_term = short_term.remember(f"{result.name}_result", result.content)
        return {
            "messages": messages,
            "tool_results": [*state["tool_results"], *results],
            "pending_tool_calls": (),
            "short_term": short_term,
        }

    def finalize(state: AgentState) -> dict[str, object]:
        try:
            decision = _parse_final_turn(state["text"])
            if decision is not None:
                verify_decision(decision, state["tool_results"])
        except StructuredOutputError as exc:
            if state["repair_attempts"] >= MAX_REPAIR_ATTEMPTS:
                return {
                    "escalation_reason": (
                        f"could not produce a verified decision after {MAX_REPAIR_ATTEMPTS} repair attempts: {exc}"
                    )
                }
            messages = [*state["messages"], _repair_message(exc)]
            return {"messages": messages, "repair_attempts": state["repair_attempts"] + 1}
        return {"answer": state["text"], "decision": decision, "done": True}

    def route_after_finalize(state: AgentState) -> str:
        if state["escalation_reason"]:
            return "escalate"
        return END if state["done"] else "call_model"

    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("dispatch_tools", dispatch_tools)
    graph.add_node("finalize", finalize)
    graph.add_node("escalate", escalate)
    graph.set_entry_point("call_model")
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {"dispatch_tools": "dispatch_tools", "finalize": "finalize", "escalate": "escalate"},
    )
    graph.add_edge("dispatch_tools", "call_model")
    graph.add_conditional_edges(
        "finalize", route_after_finalize, {END: END, "call_model": "call_model", "escalate": "escalate"}
    )
    graph.add_edge("escalate", END)
    return graph.compile()
