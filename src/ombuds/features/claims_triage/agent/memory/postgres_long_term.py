"""Postgres-backed `LongTermMemoryStore`: adapts the feature-agnostic claimant-facts repository to the protocol."""

from ombuds.features.claims_triage.agent.memory.long_term import LongTermMemory
from ombuds.platform.infrastructure.repositories import PostgresClaimantFactsRepository


class PostgresLongTermMemoryStore:
    """Durable `LongTermMemoryStore`; survives restarts and is shared across processes."""

    def __init__(self, repository: PostgresClaimantFactsRepository) -> None:
        self._repository = repository

    def load(self, claimant_id: str) -> LongTermMemory:
        return LongTermMemory(facts=self._repository.load(claimant_id))

    def save(self, claimant_id: str, memory: LongTermMemory) -> None:
        self._repository.save(claimant_id, memory.facts)
