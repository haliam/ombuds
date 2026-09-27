"""Short-term agent memory: a bounded summary of facts learned during one triage run.

Kept in `AgentState` alongside the raw `messages` transcript. Unlike `messages`, which grows every
turn of the tool-calling loop, `ShortTermMemory` holds only the facts worth restating to the model
as plain context (e.g. the latest `check_eligibility` result) — cheap to carry forward and to inject
into the system prompt without resending the full tool-result payload history.
"""

from pydantic import BaseModel, ConfigDict


class ShortTermMemory(BaseModel):
    """Facts learned so far in the current triage run, keyed by a short label (e.g. a tool name)."""

    model_config = ConfigDict(frozen=True)

    facts: dict[str, str] = {}

    def remember(self, key: str, value: str) -> "ShortTermMemory":
        """Return a new `ShortTermMemory` with `key` set to `value`, overwriting any prior value."""
        return ShortTermMemory(facts={**self.facts, key: value})

    def as_context(self) -> str | None:
        """Render the remembered facts as a system-prompt-ready block, or `None` if there aren't any."""
        if not self.facts:
            return None
        lines = "\n".join(f"- {key}: {value}" for key, value in self.facts.items())
        return f"Known facts from this run so far:\n{lines}"
