from collections.abc import Sequence

from ombuds.features.claims_triage.rag.retriever import Retriever
from ombuds.platform.infrastructure.vector_store import KbChunk, ScoredChunk
from tests.fakes import FakeEmbedder


class _FakeStore:
    """Returns canned hits and records the last query it was asked for."""

    def __init__(self, hits: list[ScoredChunk]) -> None:
        self._hits = hits
        self.last_top_k = 0

    def upsert(self, chunks: Sequence[KbChunk]) -> None:
        raise NotImplementedError

    def replace_source(self, source: str, chunks: Sequence[KbChunk]) -> None:
        raise NotImplementedError

    def search(self, embedding: Sequence[float], top_k: int) -> list[ScoredChunk]:
        self.last_top_k = top_k
        return self._hits[:top_k]


def _hit(index: int, score: float) -> ScoredChunk:
    return ScoredChunk(source="eu261.md", chunk_index=index, content=f"text {index}", score=score)


def test_retrieve_returns_citations_with_source_chunk_and_score() -> None:
    retriever = Retriever(FakeEmbedder(), _FakeStore([_hit(3, 0.9)]))

    [citation] = retriever.retrieve("delay compensation")

    assert (citation.source, citation.chunk_index, citation.snippet, citation.score) == ("eu261.md", 3, "text 3", 0.9)


def test_retrieve_drops_hits_below_the_minimum_score() -> None:
    retriever = Retriever(FakeEmbedder(), _FakeStore([_hit(0, 0.8), _hit(1, 0.19), _hit(2, 0.5)]), min_score=0.2)

    assert [c.chunk_index for c in retriever.retrieve("q")] == [0, 2]


def test_retrieve_with_nothing_relevant_returns_empty() -> None:
    assert Retriever(FakeEmbedder(), _FakeStore([_hit(0, 0.05)])).retrieve("q") == []


def test_retrieve_passes_top_k_to_the_store() -> None:
    store = _FakeStore([])

    Retriever(FakeEmbedder(), store).retrieve("q", top_k=7)

    assert store.last_top_k == 7
