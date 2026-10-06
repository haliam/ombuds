"""PostgresLongTermMemoryStore against a real database, via the same protocol the agent uses."""

from ombuds.features.claims_triage.agent.memory.long_term import LongTermMemory, LongTermMemoryStore
from ombuds.features.claims_triage.agent.memory.postgres_long_term import PostgresLongTermMemoryStore
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.repositories import PostgresClaimantFactsRepository


def test_memory_round_trips_and_survives_a_new_store_instance(pool: Pool) -> None:
    store: LongTermMemoryStore = PostgresLongTermMemoryStore(PostgresClaimantFactsRepository(pool))

    assert store.load("claimant-1") == LongTermMemory()
    store.save("claimant-1", LongTermMemory().remember("last_decision", "eligible"))

    reloaded = PostgresLongTermMemoryStore(PostgresClaimantFactsRepository(pool))
    assert reloaded.load("claimant-1").facts == {"last_decision": "eligible"}
