"""Retriever over the real seed KB in Postgres: the right document comes back for typical claim questions."""

import pytest

from ombuds.features.claims_triage.rag.ingest import KB_SEED_DIR, ingest_directory
from ombuds.features.claims_triage.rag.retriever import Retriever
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.vector_store import PgVectorStore
from tests.fakes import FakeEmbedder


@pytest.mark.parametrize(
    ("query", "expected_source"),
    [
        ("compensation amount for a flight over 3500 km", "eu261_summary.md"),
        ("notice 14 days before departure cancelled flight re-routing", "eu261_delays_cancellations.md"),
        ("technical fault or bird strike extraordinary circumstances", "eu261_extraordinary_circumstances.md"),
    ],
)
def test_top_hit_comes_from_the_relevant_document(pool: Pool, query: str, expected_source: str) -> None:
    embedder, store = FakeEmbedder(), PgVectorStore(pool)
    ingest_directory(KB_SEED_DIR, embedder, store)

    citations = Retriever(embedder, store, min_score=0.0).retrieve(query, top_k=3)

    assert citations[0].source == expected_source
