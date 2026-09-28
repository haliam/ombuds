from fastapi.testclient import TestClient

from ombuds.api_app import app
from ombuds.platform.guardrails import api as approvals_api
from ombuds.platform.guardrails.approval_gate import ApprovalGate, GuardedAction

client = TestClient(app)


def test_list_pending_returns_requests_created_by_check(monkeypatch) -> None:
    gate = ApprovalGate()
    monkeypatch.setattr(approvals_api, "list_pending_approvals", gate.list_pending)
    monkeypatch.setattr(approvals_api, "approve_request", gate.approve)
    monkeypatch.setattr(approvals_api, "deny_request", gate.deny)
    pending = gate.check(GuardedAction.LOG_CLAIM, {"claim_id": "claim-1"})

    response = client.get("/approvals")

    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert pending.request_id in ids


def test_approve_resolves_the_request(monkeypatch) -> None:
    gate = ApprovalGate()
    monkeypatch.setattr(approvals_api, "list_pending_approvals", gate.list_pending)
    monkeypatch.setattr(approvals_api, "approve_request", gate.approve)
    monkeypatch.setattr(approvals_api, "deny_request", gate.deny)
    pending = gate.check(GuardedAction.ISSUE_PAYMENT, {"claim_id": "claim-1"})

    response = client.post(
        f"/approvals/{pending.request_id}/approve", json={"approver": "ops-lead", "note": "verified"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approver"] == "ops-lead"
    assert gate.list_pending() == ()


def test_deny_resolves_the_request(monkeypatch) -> None:
    gate = ApprovalGate()
    monkeypatch.setattr(approvals_api, "list_pending_approvals", gate.list_pending)
    monkeypatch.setattr(approvals_api, "approve_request", gate.approve)
    monkeypatch.setattr(approvals_api, "deny_request", gate.deny)
    pending = gate.check(GuardedAction.ISSUE_PAYMENT, {"claim_id": "claim-1"})

    response = client.post(f"/approvals/{pending.request_id}/deny", json={"approver": "ops-lead"})

    assert response.status_code == 200
    assert response.json()["status"] == "denied"


def test_approving_unknown_request_returns_404() -> None:
    response = client.post("/approvals/no-such-id/approve", json={"approver": "ops-lead"})

    assert response.status_code == 404
