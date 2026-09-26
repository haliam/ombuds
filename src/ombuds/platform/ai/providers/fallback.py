"""Fallback provider: retries the primary model with backoff, then fails over to a secondary model.

Wraps two `LLMProvider`s that may be entirely different SDKs (Anthropic, OpenAI, ...), each raising
their own exception hierarchy — this layer can't enumerate every retryable type. Catching `Exception`
broadly below is the one intentional exception to the no-bare-except rule (see docs/code-style.md): a
call that's about to be retried or handed to the fallback model must never be swallowed silently, but
it also can't be allowed to escape without giving that fallback a chance to answer.
"""

import logging
import time
from collections.abc import Callable, Iterator
from typing import TypeVar

from ombuds.platform.ai.providers.base import LLMProvider, ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_BACKOFF_SECONDS = 1.0

T = TypeVar("T")


class FallbackProvider:
    """Runs `primary`, retrying with exponential backoff, then falls over to `fallback` if it keeps failing.

    `primary`'s own client-level retries/timeouts (see `AnthropicProvider`) handle transient network
    blips within a single call; this layer is for when the primary *model* is unavailable altogether
    (rate-limited into the ground, region outage, deprecated) and a different model should answer instead
    of the whole triage request failing.
    """

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_backoff_seconds: float = DEFAULT_BASE_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_attempts = max_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._sleep = sleep

    def run_turn(self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str) -> ProviderTurn:
        """Retry `primary.run_turn` with backoff; fall over to `fallback.run_turn` once retries are exhausted."""
        try:
            return self._with_retries("primary", lambda: self._primary.run_turn(messages, tools, system=system))
        except Exception as exc:
            logger.warning("primary provider exhausted retries (%s); falling back", exc)
            return self._fallback.run_turn(messages, tools, system=system)

    def stream_turn(
        self, messages: list[dict[str, object]], tools: list[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        """Like `run_turn`, but only falls over before any event has reached the caller.

        Once a partial stream has already been yielded, retrying or switching models would replay or
        duplicate output the caller has seen, so a mid-stream failure is raised as-is instead.
        """
        for attempt in range(1, self._max_attempts + 1):
            started = False
            try:
                for event in self._primary.stream_turn(messages, tools, system=system):
                    started = True
                    yield event
                return
            except Exception as exc:
                if started:
                    raise
                if attempt < self._max_attempts:
                    delay = self._base_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "primary stream failed before any output (attempt %d/%d): %s; retrying in %.1fs",
                        attempt,
                        self._max_attempts,
                        exc,
                        delay,
                    )
                    self._sleep(delay)
                else:
                    logger.warning("primary provider exhausted retries (%s); falling back", exc)

        yield from self._fallback.stream_turn(messages, tools, system=system)

    def _with_retries(self, label: str, call: Callable[[], T]) -> T:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return call()
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_attempts:
                    delay = self._base_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "%s provider call failed (attempt %d/%d): %s; retrying in %.1fs",
                        label,
                        attempt,
                        self._max_attempts,
                        exc,
                        delay,
                    )
                    self._sleep(delay)
        assert last_exc is not None
        raise last_exc


def build_default_provider() -> LLMProvider:
    """The provider triage uses by default: `ANTHROPIC_MODEL`, falling back to `ANTHROPIC_FALLBACK_MODEL`."""
    from ombuds.config import ANTHROPIC_FALLBACK_MODEL, ANTHROPIC_MODEL
    from ombuds.platform.ai.providers.anthropic import AnthropicProvider

    return FallbackProvider(
        primary=AnthropicProvider(model=ANTHROPIC_MODEL),
        fallback=AnthropicProvider(model=ANTHROPIC_FALLBACK_MODEL),
    )
