import logging

import pytest
from fastapi.testclient import TestClient

from ombuds.api_app import create_app
from ombuds.features.claims_triage.api import routes as claims_routes
from ombuds.features.claims_triage.application.triage_use_case import TriageResult
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.approval_gate import ApprovalGate, GuardedAction
from tests.api_auth import APPROVER, APPROVER_HEADERS, APPROVER_TOKEN, TRIAGE_HEADERS, TRIAGE_TOKEN
from tests.unit.platform.guardrails.store_fakes import executing

_CLAIM = {"claim_text": "my flight was cancelled"}
_PAYLOAD = {"claim_id": "claim-1"}


@pytest.fixture
def gate() -> ApprovalGate:
    return ApprovalGate()


@pytest.fixture
def client(gate: ApprovalGate, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        claims_routes,
        "run_triage",
        lambda *_, **__: TriageResult(claim_id="CLM-1", answer="ok", decision=None, tool_results=()),
    )
    return TestClient(create_app(executing(gate), ToolRegistry()))


def _approval_calls(request_id: str) -> list[tuple[str, str]]:
    return [
        ("get", "/approvals"),
        ("get", f"/approvals/{request_id}"),
        ("post", f"/approvals/{request_id}/approve"),
        ("post", f"/approvals/{request_id}/deny"),
        ("post", f"/approvals/{request_id}/execute"),
    ]


def _triage_calls() -> list[tuple[str, str]]:
    return [("post", "/claims/triage"), ("post", "/claims/triage/stream")]


def test_every_protected_endpoint_rejects_a_request_without_a_token(client: TestClient, gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    for method, path in _approval_calls(request.id) + _triage_calls():
        response = client.request(method, path, json=_CLAIM)
        assert response.status_code == 401, path
        assert response.headers["www-authenticate"] == "Bearer"
    assert gate.get(request.id).status == "pending"


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer wrong-token", APPROVER_TOKEN])
def test_a_malformed_or_unknown_credential_is_a_401(client: TestClient, header: str) -> None:
    for path in ("/approvals", "/claims/triage"):
        response = client.request("get" if path == "/approvals" else "post", path, headers={"Authorization": header})
        assert response.status_code == 401, path


def test_the_triage_token_cannot_reach_approvals(client: TestClient, gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    for method, path in _approval_calls(request.id):
        assert client.request(method, path, headers=TRIAGE_HEADERS).status_code == 403, path
    assert gate.get(request.id).status == "pending"


def test_the_approver_token_cannot_triage(client: TestClient) -> None:
    for method, path in _triage_calls():
        assert client.request(method, path, json=_CLAIM, headers=APPROVER_HEADERS).status_code == 403, path


def test_each_token_opens_its_own_endpoints(client: TestClient) -> None:
    assert client.post("/claims/triage", json=_CLAIM, headers=TRIAGE_HEADERS).status_code == 200
    assert client.get("/approvals", headers=APPROVER_HEADERS).status_code == 200


def test_the_approver_is_the_configured_name_and_the_body_cannot_set_it(client: TestClient, gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    forged = client.post(f"/approvals/{request.id}/approve", json={"approver": "mallory"}, headers=APPROVER_HEADERS)
    approved = client.post(f"/approvals/{request.id}/approve", json={"note": "ok"}, headers=APPROVER_HEADERS)

    assert forged.status_code == 422
    assert approved.json()["approver"] == APPROVER


@pytest.mark.parametrize("name", ["OMBUDS_TRIAGE_TOKEN", "OMBUDS_APPROVER_TOKEN", "OMBUDS_APPROVER"])
def test_any_unset_setting_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    monkeypatch.delenv(name)

    with caplog.at_level(logging.ERROR):
        triage = client.post("/claims/triage", json=_CLAIM, headers=TRIAGE_HEADERS)
        approvals = client.get("/approvals", headers=APPROVER_HEADERS)

    assert triage.status_code == approvals.status_code == 503
    assert "not configured" in caplog.text


def test_an_empty_token_is_not_a_credential(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMBUDS_TRIAGE_TOKEN", "")

    assert client.post("/claims/triage", json=_CLAIM, headers={"Authorization": "Bearer "}).status_code == 503
    assert client.post("/claims/triage", json=_CLAIM, headers=APPROVER_HEADERS).status_code == 503


def test_identical_tokens_fail_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMBUDS_APPROVER_TOKEN", TRIAGE_TOKEN)

    assert client.post("/claims/triage", json=_CLAIM, headers=TRIAGE_HEADERS).status_code == 503
    assert client.get("/approvals", headers=TRIAGE_HEADERS).status_code == 503


def test_the_docs_and_schema_stay_public(client: TestClient) -> None:
    for path in ("/openapi.json", "/docs", "/scalar"):
        assert client.get(path).status_code == 200, path
