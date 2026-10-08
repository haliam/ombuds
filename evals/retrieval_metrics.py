"""Retrieval metrics: score ranked search results against the chunks a question should find."""

from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict

ChunkKey = tuple[str, int]  # (source file, chunk_index) — the same pair the vector store keys on


class RankedHit(BaseModel):
    """One search result as the eval sees it: which chunk, and its cosine similarity."""

    model_config = ConfigDict(frozen=True)

    source: str
    chunk_index: int
    score: float

    @property
    def key(self) -> ChunkKey:
        return (self.source, self.chunk_index)


def first_relevant_rank(hits: Sequence[RankedHit], gold: Collection[ChunkKey], min_score: float = 0.0) -> int | None:
    """1-based rank of the first gold chunk among hits scoring at least `min_score`, or None if absent.

    Hits are assumed ordered best first. Hits under the floor are dropped before ranking, which is what
    the real retriever does, so the rank here is the rank the agent would see.
    """
    kept = [hit for hit in hits if hit.score >= min_score]
    for rank, hit in enumerate(kept, start=1):
        if hit.key in gold:
            return rank
    return None


def hit_rate_at_k(ranks: Sequence[int | None], k: int) -> float:
    """Fraction of questions whose first relevant chunk ranks within the top `k`."""
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float:
    """Mean of 1/rank over questions; a question with no relevant hit contributes 0."""
    if not ranks:
        return 0.0
    return sum(1 / rank for rank in ranks if rank is not None) / len(ranks)


def rejection_rate(off_topic_hits: Sequence[Sequence[RankedHit]], min_score: float) -> float:
    """Fraction of off-topic questions for which nothing scores at or above `min_score`."""
    if not off_topic_hits:
        return 0.0
    return sum(1 for hits in off_topic_hits if all(hit.score < min_score for hit in hits)) / len(off_topic_hits)
