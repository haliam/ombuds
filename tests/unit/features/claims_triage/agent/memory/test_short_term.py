from ombuds.features.claims_triage.agent.memory.short_term import ShortTermMemory


def test_as_context_is_none_when_no_facts_are_remembered() -> None:
    assert ShortTermMemory().as_context() is None


def test_remember_returns_a_new_instance_and_leaves_the_original_untouched() -> None:
    original = ShortTermMemory()

    updated = original.remember("check_eligibility_result", "eligible")

    assert original.facts == {}
    assert updated.facts == {"check_eligibility_result": "eligible"}


def test_remember_overwrites_a_prior_value_for_the_same_key() -> None:
    memory = ShortTermMemory().remember("k", "first").remember("k", "second")

    assert memory.facts == {"k": "second"}


def test_as_context_renders_every_remembered_fact() -> None:
    memory = ShortTermMemory().remember("a", "1").remember("b", "2")

    context = memory.as_context()

    assert context is not None
    assert "- a: 1" in context
    assert "- b: 2" in context
