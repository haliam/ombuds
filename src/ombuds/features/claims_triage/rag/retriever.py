"""Retriever: embed a query, search the vector store, and return cited passages above a relevance floor."""

from functools import lru_cache

from ombuds import config
from ombuds.features.claims_triage.rag.citation import Citation, to_citation
from ombuds.platform.ai.embeddings import Embedder, OpenAIEmbedder
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.infrastructure.vector_store import PgVectorStore, VectorStore

# Cosine similarity below this is treated as "nothing relevant" rather than returned as a weak match,
# so the agent isn't handed an off-topic passage to cite. Chosen from the retrieval eval sweep (`make eval`,
# ADR-0012): just under the lowest score of any answerable question's best chunk. Re-run it if the KB or model changes.
DEFAULT_MIN_SCORE = 0.35


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


@lru_cache(maxsize=1)
def default_retriever() -> Retriever:
    """The process-wide retriever over the configured Postgres and embedding model, built on first use.

    Lazy so that building the tool registry (and importing this module) needs neither a database nor an
    API key; the pool lives for the life of the process.
    """
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    return Retriever(OpenAIEmbedder(config.EMBEDDING_MODEL), PgVectorStore(pool))
