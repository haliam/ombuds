"""Postgres connection pool and the plain-SQL migration runner (ADR-0010).

Migrations are numbered `.sql` files in `migrations/`, applied in filename order and recorded in
`schema_migrations`, so applying them again is a no-op. Rows come back as dicts.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Arbitrary constant: serialises concurrent `apply_migrations` callers (e.g. API and MCP starting together).
_MIGRATION_LOCK_ID = 7_261_001

Pool: TypeAlias = ConnectionPool[Connection[DictRow]]  # noqa: UP040 - `type` statements need Python 3.12


@dataclass(frozen=True)
class Migration:
    """One migration file: its version (the filename stem, e.g. `0001_init`) and its SQL."""

    version: str
    sql: str


def create_pool(database_url: str, max_size: int = 10) -> Pool:
    """Open a pool of dict-row connections. Each `pool.connection()` block is one transaction."""
    return ConnectionPool(database_url, min_size=1, max_size=max_size, kwargs={"row_factory": dict_row}, open=True)


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Read every `*.sql` file in `directory`, ordered by filename."""
    return [Migration(path.stem, path.read_text()) for path in sorted(directory.glob("*.sql"))]


def apply_migrations(pool: Pool, migrations: list[Migration] | None = None) -> list[str]:
    """Apply any migrations not yet recorded and return the versions applied by this call."""
    pending_candidates = discover_migrations() if migrations is None else migrations
    applied: list[str] = []
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        for migration in pending_candidates:
            if migration.version in done:
                continue
            conn.execute(migration.sql.encode())
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.version,))
            applied.append(migration.version)
    return applied
