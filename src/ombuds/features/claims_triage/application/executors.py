"""Executors for the claims-triage guarded actions: what actually happens once a human approves (ADR-0009).

Each runs after its approval, and again if a crash left the request `APPROVED`, so each write is idempotent
(`ON CONFLICT DO NOTHING` on `claim_id`). Payloads are the rules-derived ones the tools submitted.
"""

from typing import Protocol

from pydantic import JsonValue

from ombuds.features.claims_triage.tools.issue_payment import ClaimLookup, ensure_claim_logged_for
from ombuds.platform.guardrails.approval_gate import ApprovalRequest, GuardedAction
from ombuds.platform.guardrails.executing_store import Executor


class ClaimWriter(ClaimLookup, Protocol):
    """Where `log_claim` writes; `PostgresClaimRepository` fits."""

    def record(self, claim_id: str, facts: JsonValue, decision: JsonValue) -> None: ...


class PaymentWriter(Protocol):
    """Where `issue_payment` records the simulated payout; `PostgresPaymentRepository` fits."""

    def record(self, claim_id: str, amount_eur: int, approval_request_id: str) -> None: ...


def build_executors(claims: ClaimWriter, payments: PaymentWriter) -> dict[GuardedAction, Executor]:
    """The executor for every `GuardedAction`, writing to `claims` and `payments`."""

    def log_claim(request: ApprovalRequest) -> None:
        payload = request.payload
        decision = {key: payload[key] for key in ("eligible", "compensation_eur", "reasons")}
        claims.record(str(payload["claim_id"]), payload["facts"], decision)

    def issue_payment(request: ApprovalRequest) -> None:
        claim_id, amount_eur = str(request.payload["claim_id"]), request.payload["amount_eur"]
        if not isinstance(amount_eur, int):
            raise TypeError(f"payment request {request.id} has a non-integer amount: {amount_eur!r}")
        ensure_claim_logged_for(claim_id, amount_eur, claims)
        payments.record(claim_id, amount_eur, request.id)

    return {GuardedAction.LOG_CLAIM: log_claim, GuardedAction.ISSUE_PAYMENT: issue_payment}
