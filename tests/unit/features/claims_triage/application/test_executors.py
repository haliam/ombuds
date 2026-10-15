import pytest

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.application.executors import build_executors
from ombuds.platform.guardrails.approval_gate import ApprovalRequest, GuardedAction
from tests.fakes import InMemoryClaims


class _Payments:
    def __init__(self) -> None:
        self.recorded: list[tuple[str, int, str]] = []

    def record(self, claim_id: str, amount_eur: int, approval_request_id: str) -> None:
        self.recorded.append((claim_id, amount_eur, approval_request_id))


def _log_request() -> ApprovalRequest:
    return ApprovalRequest(
        id="r-1",
        action=GuardedAction.LOG_CLAIM,
        payload={
            "claim_id": "c-1",
            "eligible": True,
            "compensation_eur": 250,
            "reasons": ["eligible"],
            "facts": {"distance_km": 1200},
        },
    )


def _payment_request(amount_eur: int = 250) -> ApprovalRequest:
    return ApprovalRequest(
        id="r-2",
        action=GuardedAction.ISSUE_PAYMENT,
        payload={"claim_id": "c-1", "amount_eur": amount_eur, "reasons": ["eligible"], "facts": {}},
    )


def test_the_log_claim_executor_records_the_approved_decision_and_facts() -> None:
    claims = InMemoryClaims()

    build_executors(claims, _Payments())[GuardedAction.LOG_CLAIM](_log_request())

    facts, decision = claims.claims["c-1"]
    assert facts == {"distance_km": 1200}
    assert decision == {"eligible": True, "compensation_eur": 250, "reasons": ["eligible"]}


def test_the_log_claim_executor_is_idempotent_on_claim_id() -> None:
    claims = InMemoryClaims()
    execute = build_executors(claims, _Payments())[GuardedAction.LOG_CLAIM]

    execute(_log_request())
    execute(_log_request())

    assert list(claims.claims) == ["c-1"]


def test_the_payment_executor_records_a_payout_for_a_logged_claim() -> None:
    claims, payments = InMemoryClaims(), _Payments()
    executors = build_executors(claims, payments)
    executors[GuardedAction.LOG_CLAIM](_log_request())

    executors[GuardedAction.ISSUE_PAYMENT](_payment_request())

    assert payments.recorded == [("c-1", 250, "r-2")]


def test_the_payment_executor_refuses_an_unlogged_claim_or_a_mismatched_amount() -> None:
    claims, payments = InMemoryClaims(), _Payments()
    executors = build_executors(claims, payments)

    with pytest.raises(ToolExecutionError, match="has not been logged"):
        executors[GuardedAction.ISSUE_PAYMENT](_payment_request())
    executors[GuardedAction.LOG_CLAIM](_log_request())
    with pytest.raises(ToolExecutionError, match="logged with compensation 250"):
        executors[GuardedAction.ISSUE_PAYMENT](_payment_request(amount_eur=400))

    assert payments.recorded == []
