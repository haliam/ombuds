"""Shared API-auth test helpers: the credentials every API test runs with, and the headers that present them."""

import pytest

TRIAGE_TOKEN = "test-triage-token"
APPROVER_TOKEN = "test-approver-token"
APPROVER = "ops-lead"

TRIAGE_HEADERS = {"Authorization": f"Bearer {TRIAGE_TOKEN}"}
APPROVER_HEADERS = {"Authorization": f"Bearer {APPROVER_TOKEN}"}


def configure_api_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the three API credentials in the environment, as a deployment's `.env` would."""
    monkeypatch.setenv("OMBUDS_TRIAGE_TOKEN", TRIAGE_TOKEN)
    monkeypatch.setenv("OMBUDS_APPROVER_TOKEN", APPROVER_TOKEN)
    monkeypatch.setenv("OMBUDS_APPROVER", APPROVER)
