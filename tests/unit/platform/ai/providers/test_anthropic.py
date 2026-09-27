import anthropic
import httpx2
import pytest

from ombuds.platform.ai.providers.anthropic import AnthropicProvider
from ombuds.platform.ai.providers.base import ProviderUnavailableError


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class _FakeMessages:
    """Stands in for `anthropic.Anthropic().messages`, raising a fixed error from `create`/`stream`."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def create(self, **kwargs: object) -> None:
        raise self._error

    def stream(self, **kwargs: object) -> None:
        raise self._error


class _FakeClient:
    def __init__(self, error: Exception) -> None:
        self.messages = _FakeMessages(error)


def test_run_turn_wraps_a_retryable_sdk_error_as_provider_unavailable() -> None:
    client = _FakeClient(anthropic.APIConnectionError(request=_request()))
    provider = AnthropicProvider("claude-sonnet-5", client=client)  # type: ignore[arg-type]

    with pytest.raises(ProviderUnavailableError):
        provider.run_turn([], [], system="s")


def test_run_turn_propagates_a_non_retryable_sdk_error_unchanged() -> None:
    response = httpx2.Response(400, request=_request(), json={"error": {"type": "invalid_request_error"}})
    error = anthropic.BadRequestError("bad request", response=response, body={"error": {"type": "invalid_request_error"}})
    client = _FakeClient(error)
    provider = AnthropicProvider("claude-sonnet-5", client=client)  # type: ignore[arg-type]

    with pytest.raises(anthropic.BadRequestError):
        provider.run_turn([], [], system="s")


def test_stream_turn_wraps_a_retryable_sdk_error_as_provider_unavailable() -> None:
    response = httpx2.Response(429, request=_request(), json={"error": {"type": "rate_limit_error"}})
    error = anthropic.RateLimitError("rate limited", response=response, body={"error": {"type": "rate_limit_error"}})
    client = _FakeClient(error)
    provider = AnthropicProvider("claude-sonnet-5", client=client)  # type: ignore[arg-type]

    with pytest.raises(ProviderUnavailableError):
        list(provider.stream_turn([], [], system="s"))
