"""Integration fixtures: a real Postgres + pgvector (docker compose `db` service, or `DATABASE_URL`)."""

from collections.abc import Iterator

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from ombuds import config
from ombuds.platform.infrastructure.postgres import Pool, apply_migrations, create_pool

_TABLES = "approval_requests, claims, long_term_memory, kb_chunks"


@pytest.fixture(scope="session")
def pool() -> Iterator[Pool]:
    """Pool against a migrated database; skips the whole suite with a hint if Postgres isn't reachable."""
    try:
        db_pool = create_pool(config.DATABASE_URL, max_size=10)
        db_pool.wait(timeout=5)
    except (psycopg.OperationalError, PoolTimeout) as exc:
        pytest.skip(f"Postgres not reachable ({exc}); run `docker compose up -d --wait db`")
    apply_migrations(db_pool)
    yield db_pool
    db_pool.close()


@pytest.fixture(autouse=True)
def clean_tables(request: pytest.FixtureRequest) -> None:
    """Empty the data tables before each test that uses the database."""
    if "pool" not in request.fixturenames:
        return
    db_pool: Pool = request.getfixturevalue("pool")
    with db_pool.connection() as conn:
        conn.execute(f"TRUNCATE {_TABLES}".encode())


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tag everything under tests/integration so `-m integration` / `-m "not integration"` work."""
    for item in items:
        if "tests/integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
