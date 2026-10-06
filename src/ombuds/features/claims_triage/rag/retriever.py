"""Retriever: embed a query, search the vector store, and return cited passages above a relevance floor."""

from ombuds.features.claims_triage.rag.citation import Citation, to_citation
from ombuds.platform.ai.embeddings import Embedder
from ombuds.platform.infrastructure.vector_store import VectorStore

# Cosine similarity below this is treated as "nothing relevant" rather than returned as a weak match,
# so the agent isn't handed an off-topic passage to cite. Tune against the retrieval eval set.
DEFAULT_MIN_SCORE = 0.2


class Retriever:
    """Semantic search over the knowledge base."""

    def __init__(self, embedder: Embedder, store: VectorStore, *, min_score: float = DEFAULT_MIN_SCORE) -> None:
        self._embedder = embedder
        self._store = store
        self._min_score = min_score

    def retrieve(self, query: str, top_k: int = 5) -> list[Citation]:
        """Return up to `top_k` passages for `query`, most similar first, dropping any below `min_score`."""
        (embedding,) = self._embedder.embed([query])
        hits = self._store.search(embedding, top_k)
        return [to_citation(hit) for hit in hits if hit.score >= self._min_score]
