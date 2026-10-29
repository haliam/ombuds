"""Short-term agent memory: the typed, rules-derived facts established during one triage run.

Kept in `AgentState` alongside the raw `messages` transcript. It holds only facts our own code produced —
today, the latest successful `check_eligibility` result's fields, rendered by `agent/graph.py` — never raw
tool output or model-written text. It is not injected into any prompt: the model already sees every tool
result in `messages`. It is the run's working memory that `application/triage_use_case.py` consolidates
into `LongTermMemory` when a run ends with a verified decision (agent-loop review F-06).
"""

from pydantic import BaseModel, ConfigDict


class ShortTermMemory(BaseModel):
    """Facts established so far in the current triage run, keyed by a short label (e.g. `compensation_eur`)."""

    model_config = ConfigDict(frozen=True)

    facts: dict[str, str] = {}

    def remember(self, key: str, value: str) -> "ShortTermMemory":
        """Return a new `ShortTermMemory` with `key` set to `value`, overwriting any prior value."""
        return ShortTermMemory(facts={**self.facts, key: value})
