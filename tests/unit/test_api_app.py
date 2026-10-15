import pytest
from fastapi.testclient import TestClient

from ombuds import api_app
from ombuds.features.claims_triage.application.runtime import ClaimsTriageRuntime
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.approval_gate import ApprovalGate


class _FakePool:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_the_default_app_builds_its_runtime_at_startup_and_closes_its_pool_at_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _FakePool()
    monkeypatch.setattr(api_app, "create_pool", lambda *_: pool)
    monkeypatch.setattr(api_app, "build_runtime", lambda _pool: ClaimsTriageRuntime(ApprovalGate(), ToolRegistry()))
    app = api_app.create_app()

    with TestClient(app):
        assert isinstance(app.state.approvals, ApprovalGate)
        assert isinstance(app.state.registry, ToolRegistry)
        assert not pool.closed

    assert pool.closed


def test_an_injected_store_is_used_as_given_and_opens_no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app, "create_pool", lambda *_: pytest.fail("no pool should be opened"))
    gate = ApprovalGate()

    with TestClient(api_app.create_app(gate)) as client:
        assert client.get("/approvals").json() == []
