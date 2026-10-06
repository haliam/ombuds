"""PgVectorStore against a real database with the pgvector extension."""

import pytest

from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.vector_store import EMBEDDING_DIM, KbChunk, PgVectorStore


def axis(index: int, value: float = 1.0) -> list[float]:
    """A unit-ish vector pointing along one axis, so cosine similarity between axes is exactly 0 or 1."""
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = value
    return vector


def chunk(source: str, chunk_index: int, content: str, embedding: list[float]) -> KbChunk:
    return KbChunk(source=source, chunk_index=chunk_index, content=content, embedding=embedding)


def test_search_orders_by_cosine_similarity(pool: Pool) -> None:
    store = PgVectorStore(pool)
    store.upsert(
        [
            chunk("eu261.md", 0, "delay thresholds", axis(0)),
            chunk("eu261.md", 1, "exemptions", axis(1)),
            chunk("refunds.md", 0, "refund window", [1.0 if i < 2 else 0.0 for i in range(EMBEDDING_DIM)]),
        ]
    )

    hits = store.search(axis(0), top_k=3)

    assert [h.content for h in hits] == ["delay thresholds", "refund window", "exemptions"]
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(0.7071, abs=1e-3)
    assert hits[2].score == pytest.approx(0.0)


def test_search_respects_top_k(pool: Pool) -> None:
    store = PgVectorStore(pool)
    store.upsert([chunk("a.md", i, f"c{i}", axis(i)) for i in range(5)])

    assert len(store.search(axis(0), top_k=2)) == 2


def test_upsert_replaces_same_source_and_index(pool: Pool) -> None:
    store = PgVectorStore(pool)
    store.upsert([chunk("a.md", 0, "old", axis(0))])
    store.upsert([chunk("a.md", 0, "new", axis(1))])

    hits = store.search(axis(1), top_k=5)

    assert [(h.content, round(h.score)) for h in hits] == [("new", 1)]


def test_wrong_dimension_is_rejected(pool: Pool) -> None:
    store = PgVectorStore(pool)

    with pytest.raises(ValueError, match="dimensions"):
        store.upsert([chunk("a.md", 0, "x", [1.0, 2.0])])
    with pytest.raises(ValueError, match="dimensions"):
        store.search([1.0], top_k=1)
