"""search_kb end to end: ingested documents are found through the tool registry, as the agent would call it."""

import json

from ombuds.features.claims_triage.rag.ingest import KB_SEED_DIR, ingest_directory
from ombuds.features.claims_triage.rag.retriever import Retriever
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.schemas.tool_calls import ToolCall
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.vector_store import PgVectorStore
from tests.fakes import FakeEmbedder


def test_dispatching_search_kb_returns_cited_passages(pool: Pool) -> None:
    embedder, store = FakeEmbedder(), PgVectorStore(pool)
    ingest_directory(KB_SEED_DIR, embedder, store)
    # min_score=0: FakeEmbedder similarities are low in absolute terms; ranking is what is under test.
    registry = build_tool_registry(lambda: Retriever(embedder, store, min_score=0.0))

    [result] = registry.dispatch_all(
        [ToolCall(id="1", name="search_kb", arguments={"query": "bird strike extraordinary circumstances", "top_k": 2})]
    )

    assert result.is_error is False
    hits = json.loads(result.content)["hits"]
    assert len(hits) == 2
    assert hits[0]["source"] == "eu261_extraordinary_circumstances.md"
    assert {"source", "chunk_index", "snippet", "score"} <= hits[0].keys()
