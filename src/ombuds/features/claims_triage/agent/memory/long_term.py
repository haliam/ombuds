"""Long-term agent memory: facts about a claimant that persist across separate triage runs.

Unlike `ShortTermMemory` (scoped to one run), a `LongTermMemory` survives between `run_triage` calls
for the same claimant — e.g. that they already have an open claim, or how a past claim was decided.
`LongTermMemoryStore` is a protocol so the process-lifetime `InMemoryLongTermMemoryStore` below can be
swapped for a Postgres-backed store once one exists (see W3 in `docs/ombuds_build_tasks.md`) without
changing any agent code — callers only ever depend on the protocol.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class LongTermMemory(BaseModel):
    """Facts remembered about one claimant across runs, keyed by a short label."""

    model_config = ConfigDict(frozen=True)

    facts: dict[str, str] = {}

    def remember(self, key: str, value: str) -> "LongTermMemory":
        """Return a new `LongTermMemory` with `key` set to `value`, overwriting any prior value."""
        return LongTermMemory(facts={**self.facts, key: value})

    def as_context(self) -> str | None:
        """Render the remembered facts as a system-prompt-ready block, or `None` if there aren't any."""
        if not self.facts:
            return None
        lines = "\n".join(f"- {key}: {value}" for key, value in self.facts.items())
        return f"Known facts about this claimant from past interactions:\n{lines}"


class LongTermMemoryStore(Protocol):
    """Loads and saves a claimant's `LongTermMemory`, keyed by an opaque `claimant_id`."""

    def load(self, claimant_id: str) -> LongTermMemory:
        """Return the claimant's remembered facts, or an empty `LongTermMemory` if none exist yet."""
        ...

    def save(self, claimant_id: str, memory: LongTermMemory) -> None:
        """Persist `memory` as the claimant's full current fact set, replacing what was stored before."""
        ...


class InMemoryLongTermMemoryStore:
    """Dict-backed `LongTermMemoryStore` that only lives as long as the process does.

    The default until a real store exists — nothing here is durable across restarts, so don't reach
    for this in a deployment where that matters.
    """

    def __init__(self) -> None:
        self._by_claimant: dict[str, LongTermMemory] = {}

    def load(self, claimant_id: str) -> LongTermMemory:
        return self._by_claimant.get(claimant_id, LongTermMemory())

    def save(self, claimant_id: str, memory: LongTermMemory) -> None:
        self._by_claimant[claimant_id] = memory
