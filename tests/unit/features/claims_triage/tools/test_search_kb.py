from collections.abc import Sequence

import pytest

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.rag.retriever import Retriever
from ombuds.features.claims_triage.tools.search_kb import SEARCH_KB_TOOL, SearchKbArgs, search_kb
from ombuds.platform.infrastructure.vector_store import KbChunk, ScoredChunk
from tests.fakes import DownEmbedder, FakeEmbedder


class _FakeStore:
    def __init__(self, hits: list[ScoredChunk]) -> None:
        self._hits = hits

    def upsert(self, chunks: Sequence[KbChunk]) -> None:
        raise NotImplementedError

    def replace_source(self, source: str, chunks: Sequence[KbChunk]) -> None:
        raise NotImplementedError

    def search(self, embedding: Sequence[float], top_k: int) -> list[ScoredChunk]:
        return self._hits[:top_k]


def _retriever(hits: list[ScoredChunk]) -> Retriever:
    return Retriever(FakeEmbedder(), _FakeStore(hits))


def test_search_kb_returns_hits_with_provenance() -> None:
    retriever = _retriever([ScoredChunk(source="a.md", chunk_index=2, content="text", score=0.8)])

    result = search_kb(SearchKbArgs(query="delay"), retriever)

    assert [(h.source, h.chunk_index, h.snippet, h.score) for h in result.hits] == [("a.md", 2, "text", 0.8)]


def test_search_kb_with_no_relevant_passage_returns_empty_hits() -> None:
    assert search_kb(SearchKbArgs(query="delay"), _retriever([])).hits == ()


def test_search_kb_reports_an_unavailable_embedding_provider_as_a_tool_error() -> None:
    with pytest.raises(ToolExecutionError, match="unavailable"):
        search_kb(SearchKbArgs(query="delay"), Retriever(DownEmbedder(), _FakeStore([])))


def test_search_kb_args_requires_nonempty_query() -> None:
    with pytest.raises(ValueError):
        SearchKbArgs(query="")


def test_tool_definition_args_model_is_search_kb_args() -> None:
    assert SEARCH_KB_TOOL.args_model is SearchKbArgs
