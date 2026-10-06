"""Vector store for KB chunk embeddings: a Protocol plus the pgvector implementation (ADR-0010).

Embedding generation is not here — callers pass vectors in. Cosine similarity, so `score` is
`1 - cosine_distance`: 1.0 is identical direction, 0.0 is orthogonal.
"""

from collections.abc import Sequence
from typing import Protocol

from psycopg import Connection
from psycopg.rows import DictRow
from pydantic import BaseModel, ConfigDict

from ombuds.platform.infrastructure.postgres import Pool

# Must match `vector(1536)` in migrations/0001_init.sql; changing it needs a new migration.
EMBEDDING_DIM = 1536


class KbChunk(BaseModel):
    """One chunk of a knowledge-base document with its embedding."""

    model_config = ConfigDict(frozen=True)

    source: str
    chunk_index: int
    content: str
    embedding: list[float]


class ScoredChunk(BaseModel):
    """A search hit: the chunk's text and provenance, plus its cosine similarity to the query."""

    model_config = ConfigDict(frozen=True)

    source: str
    chunk_index: int
    content: str
    score: float


class VectorStore(Protocol):
    """Stores chunk embeddings and finds the nearest ones to a query embedding."""

    def upsert(self, chunks: Sequence[KbChunk]) -> None:
        """Insert chunks, replacing any existing chunk with the same `(source, chunk_index)`."""
        ...

    def replace_source(self, source: str, chunks: Sequence[KbChunk]) -> None:
        """Make `chunks` the complete set stored for `source`, dropping any stale chunks, atomically."""
        ...

    def search(self, embedding: Sequence[float], top_k: int) -> list[ScoredChunk]:
        """Return up to `top_k` chunks, most similar first."""
        ...


def _to_vector_literal(embedding: Sequence[float]) -> str:
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(f"embedding has {len(embedding)} dimensions, expected {EMBEDDING_DIM}")
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class PgVectorStore:
    """`VectorStore` over the `kb_chunks` table (HNSW index, cosine distance)."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def upsert(self, chunks: Sequence[KbChunk]) -> None:
        with self._pool.connection() as conn:
            self._insert(conn, chunks)

    def replace_source(self, source: str, chunks: Sequence[KbChunk]) -> None:
        # One transaction, so a concurrent search never sees the source half-deleted.
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM kb_chunks WHERE source = %s", (source,))
            self._insert(conn, chunks)

    @staticmethod
    def _insert(conn: Connection[DictRow], chunks: Sequence[KbChunk]) -> None:
        rows = [(c.source, c.chunk_index, c.content, _to_vector_literal(c.embedding)) for c in chunks]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO kb_chunks (source, chunk_index, content, embedding) VALUES (%s, %s, %s, %s::vector) "
                "ON CONFLICT (source, chunk_index) DO UPDATE "
                "SET content = EXCLUDED.content, embedding = EXCLUDED.embedding",
                rows,
            )

    def search(self, embedding: Sequence[float], top_k: int) -> list[ScoredChunk]:
        literal = _to_vector_literal(embedding)
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT source, chunk_index, content, 1 - (embedding <=> %s::vector) AS score "
                "FROM kb_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
                (literal, literal, top_k),
            ).fetchall()
        return [ScoredChunk(**row) for row in rows]
