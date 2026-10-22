"""Approve -> execute end to end against Postgres: claims, payments, exactly-once, and durability."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue

from ombuds.api_app import create_app
from ombuds.features.claims_triage.application.runtime import build_runtime
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.approval_gate import ApprovalStateError, ApprovalStatus, GuardedAction
from ombuds.platform.infrastructure.postgres import Pool
from ombuds.platform.infrastructure.repositories import PostgresApprovalStore
from tests.integration.policy_fakes import PAYOUT_LIMIT_EUR, AllowAllPolicy

_LOG: dict[str, JsonValue] = {
    "claim_id": "c-1",
    "eligible": True,
    "compensation_eur": 250,
    "reasons": ["eligible"],
    "facts": {"distance_km": 1200},
}
_PAY: dict[str, JsonValue] = {"claim_id": "c-1", "amount_eur": 250, "reasons": ["eligible"], "facts": {}}


def _count(pool: Pool, table: str) -> int:
    with pool.connection() as conn:
        row = conn.execute(f"SELECT count(*) AS n FROM {table}".encode()).fetchone()
    assert row is not None
    return int(row["n"])


def test_approving_log_claim_writes_exactly_one_claims_row(pool: Pool) -> None:
    approvals = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals
    request = approvals.submit(GuardedAction.LOG_CLAIM, _LOG)
    assert _count(pool, "claims") == 0

    executed = approvals.approve(request.id, "alice")

    assert executed.status is ApprovalStatus.EXECUTED
    assert _count(pool, "claims") == 1
    with pytest.raises(ApprovalStateError):
        approvals.approve(request.id, "bob")
    with pytest.raises(ApprovalStateError):
        approvals.claim_for_execution(request.id)
    assert _count(pool, "claims") == 1


def test_concurrent_approvals_execute_exactly_once(pool: Pool) -> None:
    approvals = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals
    request = approvals.submit(GuardedAction.LOG_CLAIM, _LOG)

    def attempt(_: int) -> bool:
        try:
            approvals.approve(request.id, "alice")
        except ApprovalStateError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(8)))

    assert results.count(True) == 1
    assert _count(pool, "claims") == 1


def test_a_payment_is_recorded_only_for_a_logged_claim(pool: Pool) -> None:
    approvals = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals
    log = approvals.submit(GuardedAction.LOG_CLAIM, _LOG)
    payment = approvals.submit(GuardedAction.ISSUE_PAYMENT, _PAY)

    approvals.approve(log.id, "alice")
    approvals.approve(payment.id, "alice")

    assert _count(pool, "payments") == 1
    with pool.connection() as conn:
        row = conn.execute("SELECT amount_eur, approval_request_id FROM payments").fetchone()
    assert row == {"amount_eur": 250, "approval_request_id": payment.id}


def test_approving_a_payment_for_an_unlogged_claim_fails_and_writes_nothing(pool: Pool) -> None:
    approvals = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals
    payment = approvals.submit(GuardedAction.ISSUE_PAYMENT, _PAY)

    with pytest.raises(Exception, match="has not been logged"):
        approvals.approve(payment.id, "alice")

    assert _count(pool, "payments") == 0
    assert approvals.get(payment.id).status is ApprovalStatus.APPROVED


def test_a_failed_approval_is_recoverable_over_http_once_the_claim_is_logged(pool: Pool) -> None:
    approvals = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals
    client = TestClient(create_app(approvals, ToolRegistry()))
    payment = approvals.submit(GuardedAction.ISSUE_PAYMENT, _PAY)
    log = approvals.submit(GuardedAction.LOG_CLAIM, _LOG)

    failed = client.post(f"/approvals/{payment.id}/approve", json={"approver": "alice"})

    assert failed.status_code == 502
    assert failed.json()["status"] == "approved"
    assert _count(pool, "payments") == 0

    assert client.post(f"/approvals/{log.id}/approve", json={"approver": "alice"}).status_code == 200
    recovered = client.post(f"/approvals/{payment.id}/execute")

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "executed"
    assert _count(pool, "payments") == 1
    assert client.post(f"/approvals/{payment.id}/execute").status_code == 409
    assert _count(pool, "payments") == 1
    with pool.connection() as conn:
        kinds = [
            r["kind"]
            for r in conn.execute(
                "SELECT kind FROM audit_log WHERE approval_request_id = %s ORDER BY id", (payment.id,)
            )
        ]
    assert kinds[-2:] == ["approval_approved", "approval_executed"]


def test_pending_and_approved_requests_survive_a_restart(pool: Pool) -> None:
    pending = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals.submit(GuardedAction.LOG_CLAIM, _LOG)
    approved_before = PostgresApprovalStore(pool).submit(GuardedAction.ISSUE_PAYMENT, _PAY)
    PostgresApprovalStore(pool).approve(approved_before.id, "alice")

    restarted = build_runtime(
        pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR
    ).approvals  # a fresh process: new store objects over the same database

    assert [r.id for r in restarted.list_pending()] == [pending.id]
    assert restarted.get(approved_before.id).status is ApprovalStatus.APPROVED
