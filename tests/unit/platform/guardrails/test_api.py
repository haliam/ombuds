import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue

from ombuds.api_app import create_app
from ombuds.platform.guardrails.approval_gate import ApprovalGate, GuardedAction

_PAYLOAD: dict[str, JsonValue] = {"claim_id": "claim-1", "eligible": True, "compensation_eur": 250}


@pytest.fixture
def gate() -> ApprovalGate:
    """A scratch gate per test, injected into the app, so tests share no state."""
    return ApprovalGate()


@pytest.fixture
def client(gate: ApprovalGate) -> TestClient:
    return TestClient(create_app(gate))


def test_list_pending_shows_each_request_with_its_payload(client: TestClient, gate: ApprovalGate) -> None:
    pending = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)

    response = client.get("/approvals")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": pending.id,
            "action": "log_claim",
            "payload": _PAYLOAD,
            "status": "pending",
            "approver": None,
            "note": None,
        }
    ]


def test_get_returns_one_request_in_any_status(client: TestClient, gate: ApprovalGate) -> None:
    request = gate.submit(GuardedAction.LOG_CLAIM, _PAYLOAD)
    gate.approve(request.id, approver="ops-lead")

    response = client.get(f"/approvals/{request.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_approve_resolves_the_request(client: TestClient, gate: ApprovalGate) -> None:
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)

    response = client.post(f"/approvals/{pending.id}/approve", json={"approver": "ops-lead", "note": "verified"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approver"] == "ops-lead"
    assert gate.list_pending() == ()


def test_deny_resolves_the_request(client: TestClient, gate: ApprovalGate) -> None:
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)

    response = client.post(f"/approvals/{pending.id}/deny", json={"approver": "ops-lead"})

    assert response.status_code == 200
    assert response.json()["status"] == "denied"


def test_approving_an_already_resolved_request_returns_409(client: TestClient, gate: ApprovalGate) -> None:
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)
    gate.deny(pending.id, approver="ops-lead")

    response = client.post(f"/approvals/{pending.id}/approve", json={"approver": "someone-else"})

    assert response.status_code == 409


@pytest.mark.parametrize("path", ["/approvals/no-such-id/approve", "/approvals/no-such-id/deny"])
def test_resolving_an_unknown_request_returns_404(client: TestClient, path: str) -> None:
    response = client.post(path, json={"approver": "ops-lead"})

    assert response.status_code == 404


def test_getting_an_unknown_request_returns_404(client: TestClient, gate: ApprovalGate) -> None:
    response = client.get("/approvals/no-such-id")

    assert response.status_code == 404
