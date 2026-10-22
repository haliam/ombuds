import pytest

from ombuds import config


def test_database_url_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:secret@db:5432/x")

    assert config.database_url() == "postgresql://u:secret@db:5432/x"


def test_database_url_refuses_to_guess_a_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OMBUDS_ALLOW_DEV_DEFAULTS", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        config.database_url()


def test_the_dev_flag_opts_in_to_the_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OMBUDS_ALLOW_DEV_DEFAULTS", "1")

    assert config.database_url().endswith("@localhost:5433/ombuds")
