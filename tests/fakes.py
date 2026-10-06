"""Test doubles shared across unit and integration tests."""

import hashlib
import math
import re
from collections.abc import Sequence

from ombuds.platform.ai.providers.base import ProviderUnavailableError
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
