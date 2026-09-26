from ombuds.platform.ai.providers.anthropic import _idempotency_key


def test_idempotency_key_is_stable_for_the_same_request() -> None:
    messages: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
    key_a = _idempotency_key("claude-sonnet-5", "system", messages, [])
    key_b = _idempotency_key("claude-sonnet-5", "system", messages, [])

    assert key_a == key_b


def test_idempotency_key_changes_when_the_conversation_grows() -> None:
    base: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
    grown: list[dict[str, object]] = [*base, {"role": "assistant", "content": "hi"}]

    assert _idempotency_key("claude-sonnet-5", "system", base, []) != _idempotency_key(
        "claude-sonnet-5", "system", grown, []
    )


def test_idempotency_key_changes_with_model() -> None:
    messages: list[dict[str, object]] = [{"role": "user", "content": "hello"}]

    assert _idempotency_key("claude-sonnet-5", "system", messages, []) != _idempotency_key(
        "claude-haiku-4-5", "system", messages, []
    )
