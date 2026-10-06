"""Migration runner against a real database."""

from ombuds.platform.infrastructure.postgres import Migration, Pool, apply_migrations


def test_apply_migrations_is_idempotent(pool: Pool) -> None:
    assert apply_migrations(pool) == []


def test_apply_migrations_applies_only_new_versions(pool: Pool) -> None:
    extra = Migration("9999_test_only", "CREATE TABLE IF NOT EXISTS migration_probe (id INT);")
    try:
        assert apply_migrations(pool, [extra]) == ["9999_test_only"]
        assert apply_migrations(pool, [extra]) == []
    finally:
        with pool.connection() as conn:
            conn.execute("DROP TABLE IF EXISTS migration_probe")
            conn.execute("DELETE FROM schema_migrations WHERE version = '9999_test_only'")


def test_pgvector_extension_is_installed(pool: Pool) -> None:
    with pool.connection() as conn:
        row = conn.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'").fetchone()

    assert row is not None
