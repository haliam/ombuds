"""Escalate/retry node: routes a stuck or unverifiable triage run to human review instead of failing loud.

Reached (via `agent/graph.py`'s `route_after_model`/`route_after_finalize`) when the tool-use loop can't
converge within `MAX_TOOL_TURNS`, the model's final reply keeps failing structured-output/verification
repair after `MAX_REPAIR_ATTEMPTS`, or a turn ends with a `stop_reason` the model can't recover from on
its own (a truncated reply or a refusal — see W1 review F-09/F-10). Rather than raising and turning "the
agent couldn't reach a confident decision" — a business outcome — into a bare 500, this node marks the
run `escalated` with a human-readable reason and returns the best answer text available, so callers can
route it to a person instead of crashing.
"""

from ombuds.features.claims_triage.agent.state import AgentState

UNRECOVERABLE_STOP_REASONS = frozenset({"max_tokens", "refusal"})


def escalate(state: AgentState) -> dict[str, object]:
    """Terminate the run as escalated, using `state["escalation_reason"]` set by the node that routed here."""
    reason = state["escalation_reason"] or "escalated for an unspecified reason"
    answer = state["text"] or f"This claim could not be resolved automatically and needs human review: {reason}"
    return {"done": True, "escalated": True, "escalation_reason": reason, "answer": answer}
