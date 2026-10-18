"""The audit trail against a real database: end-to-end events through the runtime, and immutability."""

import uuid

import psycopg.errors
import pytest
from pydantic import JsonValue

from ombuds.domain.errors import PolicyDeniedError
from ombuds.features.claims_triage.application.runtime import build_runtime
from ombuds.platform.ai.schemas.tool_calls import ToolCall
from ombuds.platform.guardrails.approval_gate import GuardedAction
from ombuds.platform.guardrails.audit_log import AuditEvent, AuditKind
from ombuds.platform.guardrails.policy_engine import PolicyDecision
from ombuds.platform.infrastructure.audit_repository import PostgresAuditLog
from ombuds.platform.infrastructure.postgres import Pool
from tests.integration.policy_fakes import PAYOUT_LIMIT_EUR, AllowAllPolicy

# The audit table is append-only, so tests can't truncate it between runs; each test uses its own claim id.


def _claim_id() -> str:
    return f"audit-{uuid.uuid4()}"


def _log(claim_id: str) -> dict[str, JsonValue]:
    return {"claim_id": claim_id, "eligible": True, "compensation_eur": 250, "reasons": ["eligible"], "facts": {}}


class _DenyPolicy:
    def evaluate(self, policy_input: object) -> PolicyDecision:
        return PolicyDecision(allow=False, reasons=("payout_above_limit",), policy_version="test")


def test_a_full_approval_lifecycle_leaves_an_ordered_trail(pool: Pool) -> None:
    claim_id = _claim_id()
    approvals = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).approvals

    request = approvals.submit(GuardedAction.LOG_CLAIM, _log(claim_id))
    approvals.approve(request.id, "alice")

    trail = PostgresAuditLog(pool).for_claim(claim_id)
    assert [(e.kind, e.outcome) for e in trail] == [
        (AuditKind.POLICY_DECISION, "allow"),
        (AuditKind.APPROVAL_SUBMITTED, "pending"),
        (AuditKind.APPROVAL_APPROVED, "approved"),
        (AuditKind.APPROVAL_EXECUTED, "executed"),
    ]
    assert {e.approval_request_id for e in trail[1:]} == {request.id}


def test_a_policy_denial_is_audited_even_though_no_request_exists(pool: Pool) -> None:
    claim_id = _claim_id()
    approvals = build_runtime(pool, _DenyPolicy(), PAYOUT_LIMIT_EUR).approvals

    with pytest.raises(PolicyDeniedError):
        approvals.submit(GuardedAction.ISSUE_PAYMENT, {"claim_id": claim_id, "amount_eur": 900})

    (event,) = PostgresAuditLog(pool).for_claim(claim_id)
    assert (event.kind, event.outcome, event.approval_request_id) == (AuditKind.POLICY_DECISION, "deny", None)
    assert event.detail == {"reasons": ["payout_above_limit"], "policy_version": "test"}


def test_a_tool_call_through_the_runtime_registry_is_audited(pool: Pool) -> None:
    claim_id = _claim_id()
    registry = build_runtime(pool, AllowAllPolicy(), PAYOUT_LIMIT_EUR).registry

    registry.dispatch_all([ToolCall(id="t1", name="log_claim", arguments={"claim_id": claim_id})])

    kinds = [e.kind for e in PostgresAuditLog(pool).for_claim(claim_id)]
    assert AuditKind.TOOL_CALL in kinds


def test_audit_rows_cannot_be_updated_deleted_or_truncated(pool: Pool) -> None:
    claim_id = _claim_id()
    event = AuditEvent(kind=AuditKind.TOOL_CALL, subject="search_kb", outcome="ok", claim_id=claim_id)
    PostgresAuditLog(pool).record(event)

    for statement in (
        "UPDATE audit_log SET outcome = 'tampered'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        with pytest.raises(psycopg.errors.RaiseException), pool.connection() as conn:
            conn.execute(statement.encode())

    assert [e.outcome for e in PostgresAuditLog(pool).for_claim(claim_id)] == ["ok"]


def test_an_event_is_stamped_with_the_active_trace_id(pool: Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    claim_id = _claim_id()
    monkeypatch.setattr("ombuds.platform.infrastructure.audit_repository.current_trace_id", lambda: "ab" * 16)
    audit = PostgresAuditLog(pool)

    audit.record(AuditEvent(kind=AuditKind.TOOL_CALL, subject="search_kb", outcome="ok", claim_id=claim_id))

    assert [e.trace_id for e in audit.for_claim(claim_id)] == ["ab" * 16]
