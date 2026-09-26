from collections.abc import Iterator

import pytest

from ombuds.platform.ai.providers.base import ProviderTurn
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

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        self.calls += 1
        if self._fail_times is not None and self.calls > self._fail_times:
            return _TURN
        raise self._error

    def stream_turn(
        self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        if self._fail_times is not None and self.calls > self._fail_times:
            yield TurnDone(text="ok", tool_calls=(), stop_reason="end_turn", content=[])
            return
        raise self._error


class _OkProvider:
    def __init__(self) -> None:
        self.calls = 0

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        self.calls += 1
        return _TURN

    def stream_turn(
        self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        yield TurnDone(text="ok", tool_calls=(), stop_reason="end_turn", content=[])


class _MidStreamFailure:
    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        raise AssertionError("not used")

    def stream_turn(
        self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        yield TextDelta(text="partial")
        raise ConnectionError("dropped mid-stream")


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
    primary = _FailingProvider(ConnectionError("blip"), fail_times=2)
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=3, sleep=_no_sleep)

    result = provider.run_turn([], [], system="s")

    assert result == _TURN
    assert primary.calls == 3
    assert fallback.calls == 0


def test_run_turn_falls_back_once_primary_retries_are_exhausted() -> None:
    primary = _FailingProvider(ConnectionError("down"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=2, sleep=_no_sleep)

    result = provider.run_turn([], [], system="s")

    assert result == _TURN
    assert primary.calls == 2
    assert fallback.calls == 1


def test_stream_turn_falls_back_if_primary_fails_before_any_output() -> None:
    primary = _FailingProvider(ConnectionError("down"))
    fallback = _OkProvider()
    provider = FallbackProvider(primary, fallback, max_attempts=2, sleep=_no_sleep)

    events = list(provider.stream_turn([], [], system="s"))

    assert isinstance(events[-1], TurnDone)
    assert fallback.calls == 1


def test_stream_turn_reraises_mid_stream_failure_without_fallback() -> None:
    provider = FallbackProvider(_MidStreamFailure(), _OkProvider(), sleep=_no_sleep)

    with pytest.raises(ConnectionError):
        list(provider.stream_turn([], [], system="s"))
