"""AgentState: the LangGraph state threaded through every node of the triage tool-calling loop."""

from typing import TypedDict

from ombuds.features.claims_triage.agent.memory.long_term import LongTermMemory
from ombuds.features.claims_triage.agent.memory.short_term import ShortTermMemory
from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolResult


class AgentState(TypedDict):
    """State for the tool-calling loop graph (`agent/graph.py`).

    `turns` counts `call_model` invocations, bounding the tool-use loop the same way
    `MAX_TOOL_TURNS` bounded the old hand-rolled loop. `repair_attempts` bounds retries of a
    final reply that fails structured-output validation or `verify_decision`. `pending_tool_calls`
    and `text` hold the latest model turn's output between `call_model` and the nodes that consume
    it; `done` marks that `finalize` reached an answer rather than looping back for a repair.

    `short_term` accumulates facts learned during this run (e.g. tool results) and is injected back
    into the model's system prompt each turn; `long_term` holds whatever was already known about this
    claimant from past runs (see `agent/memory/long_term.py`) and is read-only within the graph —
    `application/triage_use_case.py` owns persisting updates back to the `LongTermMemoryStore`.
    """

    messages: list[dict[str, object]]
    tool_results: list[ToolResult]
    pending_tool_calls: tuple[ToolCall, ...]
    text: str
    turns: int
    repair_attempts: int
    answer: str | None
    decision: TriageDecision | None
    done: bool
    short_term: ShortTermMemory
    long_term: LongTermMemory
