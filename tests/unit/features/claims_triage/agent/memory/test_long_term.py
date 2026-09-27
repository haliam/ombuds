from ombuds.features.claims_triage.agent.memory.long_term import InMemoryLongTermMemoryStore, LongTermMemory


def test_as_context_is_none_when_no_facts_are_remembered() -> None:
    assert LongTermMemory().as_context() is None


def test_remember_returns_a_new_instance_and_leaves_the_original_untouched() -> None:
    original = LongTermMemory()

    updated = original.remember("last_decision", "eligible for EUR 250")

    assert original.facts == {}
    assert updated.facts == {"last_decision": "eligible for EUR 250"}


def test_in_memory_store_returns_empty_memory_for_an_unknown_claimant() -> None:
    store = InMemoryLongTermMemoryStore()

    assert store.load("unknown@example.com") == LongTermMemory()


def test_in_memory_store_round_trips_a_saved_memory() -> None:
    store = InMemoryLongTermMemoryStore()
    memory = LongTermMemory().remember("last_decision", "eligible for EUR 250")

    store.save("claimant@example.com", memory)

    assert store.load("claimant@example.com") == memory


def test_in_memory_store_keeps_claimants_separate() -> None:
    store = InMemoryLongTermMemoryStore()
    store.save("a@example.com", LongTermMemory().remember("k", "a"))
    store.save("b@example.com", LongTermMemory().remember("k", "b"))

    assert store.load("a@example.com").facts == {"k": "a"}
    assert store.load("b@example.com").facts == {"k": "b"}
