"""Citation: the provenance of a retrieved passage, so a decision can point back to its policy source."""

from pydantic import BaseModel, ConfigDict

from ombuds.platform.infrastructure.vector_store import ScoredChunk


class Citation(BaseModel):
    """A retrieved passage with where it came from: document name, chunk position and similarity score."""

    model_config = ConfigDict(frozen=True)

    source: str
    chunk_index: int
    snippet: str
    score: float


def to_citation(chunk: ScoredChunk) -> Citation:
    """Turn a search hit into a citation; the snippet is the chunk's full text."""
    return Citation(source=chunk.source, chunk_index=chunk.chunk_index, snippet=chunk.content, score=chunk.score)
