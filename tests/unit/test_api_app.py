import pytest
from fastapi.testclient import TestClient

from ombuds import api_app
from ombuds.features.claims_triage.api import routes as claims_routes
from ombuds.features.claims_triage.application.runtime import ClaimsTriageRuntime
from ombuds.platform.ai.budget import BudgetExceededError
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.approval_gate import ApprovalGate
from ombuds.platform.guardrails.executing_store import ExecutingApprovalStore
from tests.api_auth import APPROVER_HEADERS, TRIAGE_HEADERS
from tests.unit.platform.guardrails.store_fakes import executing


class _FakePool:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_the_default_app_builds_its_runtime_at_startup_and_closes_its_pool_at_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _FakePool()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setattr(api_app, "create_pool", lambda *_: pool)
    monkeypatch.setattr(
        api_app, "build_runtime", lambda *_: ClaimsTriageRuntime(executing(ApprovalGate()), ToolRegistry())
    )
    app = api_app.create_app()

    with TestClient(app):
        assert isinstance(app.state.approvals, ExecutingApprovalStore)
        assert isinstance(app.state.registry, ToolRegistry)
        assert not pool.closed

    assert pool.closed


def test_an_injected_store_is_used_as_given_and_opens_no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app, "create_pool", lambda *_: pytest.fail("no pool should be opened"))
    gate = executing(ApprovalGate())

    with TestClient(api_app.create_app(gate)) as client:
        assert client.get("/approvals", headers=APPROVER_HEADERS).json() == []


def test_the_scalar_api_reference_is_served_and_points_at_the_openapi_schema() -> None:
    with TestClient(api_app.create_app(executing(ApprovalGate()))) as client:
        response = client.get("/scalar")

    assert response.status_code == 200
    assert 'data-url="/openapi.json"' in response.text
    assert "/scalar" not in client.get("/openapi.json").json()["paths"]


def test_a_spent_llm_budget_is_a_429_not_a_500(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise BudgetExceededError("LLM spend cap reached")

    monkeypatch.setattr(claims_routes, "run_triage", refuse)

    with TestClient(api_app.create_app(executing(ApprovalGate()), ToolRegistry())) as client:
        response = client.post("/claims/triage", json={"claim_text": "my flight was cancelled"}, headers=TRIAGE_HEADERS)

    assert response.status_code == 429
    assert "spend cap" in response.json()["detail"]
