from collections.abc import Iterator, Sequence

import pytest

from ombuds.platform.ai.budget import BudgetExceededError
from ombuds.platform.ai.providers.base import ProviderTurn, ProviderUnavailableError
from ombuds.platform.ai.providers.fallback import FallbackProvider
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TextDelta, TurnDone

_TURN = ProviderTurn(text="hello", tool_calls=(), stop_reason="end_turn", content=[])


class _FailingProvider:
    """Raises `error` on every call, or every call up to `fail_times` if given."""

    def __init__(self, error: Exception, *, fail_times: int | None = None) -> None:
        self._error = error
        self._fail_times = fail_times
        self.calls = 0

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        self.calls += 1
        if self._fail_times is not None and self.calls > self._fail_times:
            return _TURN
        raise self._error

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        if self._fail_times is not None and self.calls > self._fail_times:
            yield TurnDone(text="ok", tool_calls=(), stop_reason="end_turn", content=[])
            return
        raise self._error


class _OkProvider:
    def __init__(self) -> None:
        self.calls = 0

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        self.calls += 1
        return _TURN

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        yield TurnDone(text="ok", tool_calls=(), stop_reason="end_turn", content=[])


class _MidStreamFailure:
    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        raise AssertionError("not used")

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        yield TextDelta(text="partial")
        raise ProviderUnavailableError("dropped mid-stream")


def _no_sleep(_seconds: float) -> None:
    pass


def test_run_turn_succeeds_without_retry_when_primary_works() -> None:
    primary = _OkProvider()
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, sleep=_no_sleep)

    result = provider.run_turn([], [], system="s")

    assert result == _TURN
    assert primary.calls == 1
    assert fallback.calls == 0


def test_run_turn_retries_primary_before_succeeding() -> None:
    primary = _FailingProvider(ProviderUnavailableError("blip"), fail_times=2)
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=3, sleep=_no_sleep)

    result = provider.run_turn([], [], system="s")

    assert result == _TURN
    assert primary.calls == 3
    assert fallback.calls == 0


def test_run_turn_falls_back_once_primary_retries_are_exhausted() -> None:
    primary = _FailingProvider(ProviderUnavailableError("down"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=2, sleep=_no_sleep)

    result = provider.run_turn([], [], system="s")

    assert result == _TURN
    assert primary.calls == 2
    assert fallback.calls == 1


def test_run_turn_propagates_non_provider_unavailable_errors_without_retry_or_fallback() -> None:
    """A bug or a non-retryable failure (a 4xx, our own parsing error) must not trigger retry/fallover."""
    primary = _FailingProvider(ValueError("not a provider-availability problem"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=3, sleep=_no_sleep)

    with pytest.raises(ValueError, match="not a provider-availability problem"):
        provider.run_turn([], [], system="s")

    assert primary.calls == 1
    assert fallback.calls == 0


def test_stream_turn_falls_back_if_primary_fails_before_any_output() -> None:
    primary = _FailingProvider(ProviderUnavailableError("down"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=2, sleep=_no_sleep)

    events = list(provider.stream_turn([], [], system="s"))

    assert isinstance(events[-1], TurnDone)
    assert fallback.calls == 1


def test_stream_turn_reraises_mid_stream_failure_without_fallback() -> None:
    provider = FallbackProvider(_MidStreamFailure(), _OkProvider(), sleep=_no_sleep)

    with pytest.raises(ProviderUnavailableError):
        list(provider.stream_turn([], [], system="s"))


def test_stream_turn_propagates_non_provider_unavailable_errors_without_fallback() -> None:
    primary = _FailingProvider(ValueError("not a provider-availability problem"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=3, sleep=_no_sleep)

    with pytest.raises(ValueError, match="not a provider-availability problem"):
        list(provider.stream_turn([], [], system="s"))

    assert fallback.calls == 0


def test_run_turn_does_not_fail_over_on_budget_exceeded() -> None:
    """ADR-0018: a spent budget must not be dodged by switching to the fallback model."""
    primary = _FailingProvider(BudgetExceededError("cap reached"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=3, sleep=_no_sleep)

    with pytest.raises(BudgetExceededError):
        provider.run_turn([], [], system="s")

    assert primary.calls == 1
    assert fallback.calls == 0


def test_stream_turn_does_not_fail_over_on_budget_exceeded() -> None:
    primary = _FailingProvider(BudgetExceededError("cap reached"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=3, sleep=_no_sleep)

    with pytest.raises(BudgetExceededError):
        list(provider.stream_turn([], [], system="s"))

    assert primary.calls == 1
    assert fallback.calls == 0
