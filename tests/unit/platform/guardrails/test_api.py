import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue

from ombuds.api_app import create_app
from ombuds.domain.errors import ToolExecutionError
from ombuds.platform.guardrails.approval_gate import ApprovalGate, ApprovalRequest, GuardedAction
from ombuds.platform.guardrails.audit_log import AuditKind
from ombuds.platform.guardrails.audited_store import AuditedApprovalStore
from ombuds.platform.guardrails.executing_store import ExecutingApprovalStore
from ombuds.platform.guardrails.policy_checked_store import PolicyCheckedApprovalStore
from ombuds.platform.guardrails.policy_engine import PolicyDecision
from tests.unit.platform.guardrails.audit_fakes import RecordingAuditLog
from tests.unit.platform.guardrails.store_fakes import executing

_PAYLOAD: dict[str, JsonValue] = {"claim_id": "claim-1", "eligible": True, "compensation_eur": 250}


@pytest.fixture
def gate() -> ApprovalGate:
    """A scratch gate per test, injected into the app, so tests share no state."""
    return ApprovalGate()


@pytest.fixture
def client(gate: ApprovalGate) -> TestClient:
    return TestClient(create_app(executing(gate)))


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
    assert body["status"] == "executed"
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


@pytest.mark.parametrize(
    "path", ["/approvals/no-such-id/approve", "/approvals/no-such-id/deny", "/approvals/no-such-id/execute"]
)
def test_resolving_an_unknown_request_returns_404(client: TestClient, path: str) -> None:
    response = client.post(path, json={"approver": "ops-lead"})

    assert response.status_code == 404


def test_getting_an_unknown_request_returns_404(client: TestClient, gate: ApprovalGate) -> None:
    response = client.get("/approvals/no-such-id")

    assert response.status_code == 404


class _FlakyExecutor:
    """Fails with `error` until `heal()` is called, then records what it ran."""

    def __init__(self, error: Exception) -> None:
        self.error: Exception | None = error
        self.executed: list[str] = []

    def heal(self) -> None:
        self.error = None

    def __call__(self, request: ApprovalRequest) -> None:
        if self.error is not None:
            raise self.error
        self.executed.append(request.id)


class _AllowAll:
    def evaluate(self, policy_input: object) -> PolicyDecision:
        return PolicyDecision(allow=True)


def _app_over_real_stack(
    gate: ApprovalGate, executor: _FlakyExecutor, audit: RecordingAuditLog, *, raise_server_exceptions: bool = True
) -> TestClient:
    """The runtime's decorator stack (policy -> executing -> audited) over an in-memory gate."""
    executing_store = ExecutingApprovalStore(
        AuditedApprovalStore(gate, audit), {action: executor for action in GuardedAction}
    )
    approvals = PolicyCheckedApprovalStore(executing_store, _AllowAll(), {"max_payout_eur": 400}, audit)
    return TestClient(create_app(approvals), raise_server_exceptions=raise_server_exceptions)


def test_a_failed_executor_is_a_502_naming_the_request_and_it_stays_approved() -> None:
    gate, audit = ApprovalGate(), RecordingAuditLog()
    executor = _FlakyExecutor(ToolExecutionError("claim c-1 has not been logged"))
    client = _app_over_real_stack(gate, executor, audit)
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)

    response = client.post(f"/approvals/{pending.id}/approve", json={"approver": "ops-lead"})

    assert response.status_code == 502
    body = response.json()
    assert body["request_id"] == pending.id
    assert body["status"] == "approved"
    assert "has not been logged" in body["detail"]
    assert f"/approvals/{pending.id}/execute" in body["detail"]
    assert gate.get(pending.id).status.value == "approved"
    assert executor.executed == []


def test_execute_runs_the_executor_once_after_the_cause_is_fixed_and_the_audit_trail_shows_it() -> None:
    gate, audit = ApprovalGate(), RecordingAuditLog()
    executor = _FlakyExecutor(ToolExecutionError("claim c-1 has not been logged"))
    client = _app_over_real_stack(gate, executor, audit)
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)
    client.post(f"/approvals/{pending.id}/approve", json={"approver": "ops-lead"})
    executor.heal()

    response = client.post(f"/approvals/{pending.id}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    assert executor.executed == [pending.id]
    assert [e.kind for e in audit.events] == [AuditKind.APPROVAL_APPROVED, AuditKind.APPROVAL_EXECUTED]
    assert client.post(f"/approvals/{pending.id}/execute").status_code == 409
    assert executor.executed == [pending.id]


def test_execute_that_fails_again_is_a_502_and_the_request_stays_approved() -> None:
    gate, audit = ApprovalGate(), RecordingAuditLog()
    client = _app_over_real_stack(gate, _FlakyExecutor(ToolExecutionError("still not logged")), audit)
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)
    client.post(f"/approvals/{pending.id}/approve", json={"approver": "ops-lead"})

    response = client.post(f"/approvals/{pending.id}/execute")

    assert response.status_code == 502
    assert response.json()["status"] == "approved"


@pytest.mark.parametrize("final", ["pending", "denied", "executed"])
def test_execute_on_a_request_that_is_not_approved_is_a_409_and_writes_nothing(final: str) -> None:
    gate, audit = ApprovalGate(), RecordingAuditLog()
    executor = _FlakyExecutor(ToolExecutionError("unused"))
    executor.heal()
    client = _app_over_real_stack(gate, executor, audit)
    request = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)
    if final == "denied":
        gate.deny(request.id, "ops-lead")
    elif final == "executed":
        gate.approve(request.id, "ops-lead")
        gate.claim_for_execution(request.id)

    response = client.post(f"/approvals/{request.id}/execute")

    assert response.status_code == 409
    assert executor.executed == []
    assert audit.events == []
    assert gate.get(request.id).status.value == final


def test_an_unexpected_executor_error_still_propagates_and_is_logged_with_the_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gate, audit = ApprovalGate(), RecordingAuditLog()
    client = _app_over_real_stack(gate, _FlakyExecutor(RuntimeError("boom")), audit, raise_server_exceptions=False)
    pending = gate.submit(GuardedAction.ISSUE_PAYMENT, _PAYLOAD)

    with caplog.at_level(logging.ERROR):
        response = client.post(f"/approvals/{pending.id}/approve", json={"approver": "ops-lead"})

    assert response.status_code == 500
    assert pending.id in caplog.text
    assert gate.get(pending.id).status.value == "approved"
