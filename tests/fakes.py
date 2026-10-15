"""Test doubles shared across unit and integration tests."""

import hashlib
import math
import re
from collections.abc import Iterator, Sequence

from pydantic import JsonValue

from ombuds.platform.ai.providers.base import ProviderTurn, ProviderUnavailableError
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TextDelta, ToolCallDelta, TurnDone
from ombuds.platform.infrastructure.vector_store import EMBEDDING_DIM


class FakeEmbedder:
    """Deterministic bag-of-words embedder: texts sharing words get a high cosine similarity.

    Each lower-cased word bumps one hash-chosen dimension, then the vector is normalised. No network,
    and similar texts land near each other, so retrieval tests can assert on ranking.
    """

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for word in re.findall(r"\w+", text.lower()):
            vector[int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


class DownEmbedder:
    """An embedder whose provider is unavailable, for testing how callers surface that."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise ProviderUnavailableError("embedding provider is down")


class ScriptedProvider:
    """An `LLMProvider` that replays a fixed sequence of turns, ignoring what it is sent — no real API calls."""

    def __init__(self, turns: Sequence[ProviderTurn]) -> None:
        self._turns = list(turns)
        self.calls = 0

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        self.calls += 1
        return self._turns.pop(0)

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self.calls += 1
        turn = self._turns.pop(0)
        if turn.text:
            yield TextDelta(text=turn.text)
        for call in turn.tool_calls:
            yield ToolCallDelta(call=call)
        yield TurnDone(text=turn.text, tool_calls=turn.tool_calls, stop_reason=turn.stop_reason, content=turn.content)


class InMemoryClaims:
    """In-memory logged claims and payouts, standing in for the Postgres claim and payment repositories."""

    def __init__(self) -> None:
        self.claims: dict[str, tuple[JsonValue, dict[str, JsonValue]]] = {}
        self.payments: dict[str, tuple[int, str]] = {}

    def record(self, claim_id: str, facts: JsonValue, decision: JsonValue) -> None:
        assert isinstance(decision, dict)
        self.claims.setdefault(claim_id, (facts, decision))

    def decision_for(self, claim_id: str) -> dict[str, JsonValue] | None:
        logged = self.claims.get(claim_id)
        return None if logged is None else logged[1]

    def record_payment(self, claim_id: str, amount_eur: int, approval_request_id: str) -> None:
        self.payments.setdefault(claim_id, (amount_eur, approval_request_id))
