"""Ingest: turn the markdown documents in a directory into embedded chunks in the vector store."""

from pathlib import Path

from ombuds import config
from ombuds.features.claims_triage.rag.chunking import chunk_document
from ombuds.features.claims_triage.verticals import airline
from ombuds.platform.ai.embeddings import Embedder, OpenAIEmbedder
from ombuds.platform.infrastructure.postgres import apply_migrations, create_pool
from ombuds.platform.infrastructure.vector_store import KbChunk, PgVectorStore, VectorStore

KB_SEED_DIR = Path(airline.__file__).parent / "kb_seed"


def ingest_directory(directory: Path, embedder: Embedder, store: VectorStore) -> dict[str, int]:
    """Chunk, embed and store every `*.md` file in `directory`; return the chunk count per source.

    Re-running is safe: each source is replaced wholesale, so edited documents leave no stale chunks.
    `source` is the file name, which is what citations show.
    """
    counts: dict[str, int] = {}
    for path in sorted(directory.glob("*.md")):
        chunks = chunk_document(path.name, path.read_text())
        embeddings = embedder.embed([c.content for c in chunks])
        store.replace_source(
            path.name,
            [
                KbChunk(source=c.source, chunk_index=c.chunk_index, content=c.content, embedding=e)
                for c, e in zip(chunks, embeddings, strict=True)
            ],
        )
        counts[path.name] = len(chunks)
    return counts


def main() -> None:
    """Ingest the airline KB seed documents using the configured Postgres and embedding model."""
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    try:
        apply_migrations(pool)
        counts = ingest_directory(KB_SEED_DIR, OpenAIEmbedder(config.EMBEDDING_MODEL), PgVectorStore(pool))
    finally:
        pool.close()
    for source, count in counts.items():
        print(f"{source}: {count} chunks")


if __name__ == "__main__":
    main()
