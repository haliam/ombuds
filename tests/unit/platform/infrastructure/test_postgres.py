"""Unit tests for migration discovery (the runner itself is covered by the integration tests)."""

from pathlib import Path

from ombuds.platform.infrastructure.postgres import MIGRATIONS_DIR, Migration, discover_migrations


def test_discover_migrations_orders_by_filename(tmp_path: Path) -> None:
    (tmp_path / "0002_b.sql").write_text("SELECT 2;")
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "notes.txt").write_text("ignored")

    assert discover_migrations(tmp_path) == [Migration("0001_a", "SELECT 1;"), Migration("0002_b", "SELECT 2;")]


def test_shipped_migrations_start_with_init() -> None:
    versions = [m.version for m in discover_migrations(MIGRATIONS_DIR)]

    assert versions[0] == "0001_init"
    assert versions == sorted(versions)
