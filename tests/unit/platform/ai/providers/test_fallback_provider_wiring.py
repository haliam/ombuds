"""Pins that `build_default_provider()` actually passes config through to the underlying providers.

Separate from `test_fallback.py` (which exercises `FallbackProvider`'s retry/fallover logic against fakes)
and `test_anthropic.py` (which only covers `_idempotency_key`) — this is the one place that would have
caught the configured timeout/max-retries silently going nowhere.
"""

from ombuds import config
from ombuds.platform.ai.providers.anthropic import AnthropicProvider
from ombuds.platform.ai.providers.fallback import FallbackProvider, build_default_provider
from ombuds.platform.ai.providers.traced import TracedProvider


def test_build_default_provider_passes_configured_model_timeout_and_retries(monkeypatch) -> None:
    monkeypatch.setattr(config, "ANTHROPIC_MODEL", "test-primary-model")
    monkeypatch.setattr(config, "ANTHROPIC_FALLBACK_MODEL", "test-fallback-model")
    monkeypatch.setattr(config, "ANTHROPIC_TIMEOUT_SECONDS", 12.5)
    monkeypatch.setattr(config, "ANTHROPIC_MAX_RETRIES", 4)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    provider = build_default_provider()

    assert isinstance(provider, FallbackProvider)
    traced_primary, traced_fallback = provider._primary, provider._fallback  # private, no public getter
    assert isinstance(traced_primary, TracedProvider)
    assert isinstance(traced_fallback, TracedProvider)
    primary, fallback = traced_primary._inner, traced_fallback._inner
    assert isinstance(primary, AnthropicProvider)
    assert isinstance(fallback, AnthropicProvider)
    assert primary._model == "test-primary-model"
    assert fallback._model == "test-fallback-model"
    assert primary._client.timeout == 12.5
    assert primary._client.max_retries == 4
    assert fallback._client.timeout == 12.5
    assert fallback._client.max_retries == 4
