"""Ingest against real Postgres: chunks are stored, searchable, and replaced cleanly on re-ingest."""

from pathlib import Path

from ombuds.features.claims_triage.rag.ingest import KB_SEED_DIR, ingest_directory
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.vector_store import PgVectorStore
from tests.fakes import FakeEmbedder


def _count(pool: Pool, source: str) -> int:
    with pool.connection() as conn:
        row = conn.execute("SELECT count(*) AS n FROM kb_chunks WHERE source = %s", (source,)).fetchone()
    assert row is not None
    return int(row["n"])


def test_seed_documents_are_ingested_and_found_by_search(pool: Pool) -> None:
    embedder = FakeEmbedder()
    store = PgVectorStore(pool)

    counts = ingest_directory(KB_SEED_DIR, embedder, store)

    assert set(counts) == {p.name for p in KB_SEED_DIR.glob("*.md")}
    assert all(n > 0 for n in counts.values())
    hit = store.search(embedder.embed(["strikes by air traffic controllers extraordinary circumstances"])[0], 1)[0]
    assert hit.source == "eu261_extraordinary_circumstances.md"


def test_reingesting_an_edited_document_leaves_no_stale_chunks(pool: Pool, tmp_path: Path) -> None:
    doc = tmp_path / "policy.md"
    store = PgVectorStore(pool)
    doc.write_text("# One\nfirst\n\n# Two\nsecond\n\n# Three\nthird")
    ingest_directory(tmp_path, FakeEmbedder(), store)
    assert _count(pool, "policy.md") == 3

    doc.write_text("# Only\nremaining")
    ingest_directory(tmp_path, FakeEmbedder(), store)

    assert _count(pool, "policy.md") == 1
