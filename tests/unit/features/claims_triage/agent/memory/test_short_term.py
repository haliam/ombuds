from ombuds.features.claims_triage.agent.memory.short_term import ShortTermMemory


def test_remember_returns_a_new_instance_and_leaves_the_original_untouched() -> None:
    original = ShortTermMemory()

    updated = original.remember("compensation_eur", "250")

    assert original.facts == {}
    assert updated.facts == {"compensation_eur": "250"}


def test_remember_overwrites_a_prior_value_for_the_same_key() -> None:
    memory = ShortTermMemory().remember("k", "first").remember("k", "second")

    assert memory.facts == {"k": "second"}
