"""Tool: issue_payment. State-changing — only ever *submits* an approval request, never executes (ADR-0009).

Not offered to the triage agent (see `tools.AGENT_TOOL_NAMES`): a payment is a downstream action on an
approved claim, and stays exposed over MCP for operators.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.features.claims_triage.verticals.airline.rules import evaluate
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.guardrails.approval_gate import ApprovalStatus, ApprovalStore, GuardedAction


class ClaimLookup(Protocol):
    """Read access to logged claims; `PostgresClaimRepository` fits."""

    def decision_for(self, claim_id: str) -> dict[str, JsonValue] | None: ...


class IssuePaymentArgs(BaseModel):
    """The claim to pay and the flight facts its compensation is derived from — never an amount.

    The amount comes from the rules engine, not the caller (W2 review F-04), and a payment requires a logged
    claim whose recorded amount matches it (ADR-0009).
    """

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    disruption: FlightDisruption


class IssuePaymentResult(BaseModel):
    """Outcome of an issue_payment call: the approval request it submitted, and that request's current status."""

    model_config = ConfigDict(frozen=True)

    approval_request_id: str
    amount_eur: int
    status: ApprovalStatus


ISSUE_PAYMENT_TOOL = ToolDefinition(
    name="issue_payment",
    description=(
        "Disburse compensation for a claim. State-changing: submits the payment for human approval. "
        "Takes the flight facts; the amount is computed by the EU261 rules engine, never supplied."
    ),
    args_model=IssuePaymentArgs,
)


def ensure_claim_logged_for(claim_id: str, amount_eur: int, claims: ClaimLookup) -> None:
    """Raise `ToolExecutionError` unless `claim_id` was logged with exactly `amount_eur` compensation.

    Checked when a payment is requested and again when it executes, so neither a payment for an unlogged
    claim nor one that disagrees with the logged decision can be approved or paid.
    """
    decision = claims.decision_for(claim_id)
    if decision is None:
        raise ToolExecutionError(f"claim {claim_id} has not been logged; log it before issuing a payment")
    if decision.get("compensation_eur") != amount_eur:
        raise ToolExecutionError(
            f"claim {claim_id} was logged with compensation {decision.get('compensation_eur')} EUR, "
            f"not the {amount_eur} EUR payment requested"
        )


def issue_payment(args: IssuePaymentArgs, approvals: ApprovalStore, claims: ClaimLookup) -> IssuePaymentResult:
    """Submit a payment for human approval, with the amount the rules engine derives from `args.disruption`.

    Raises `ToolExecutionError` when the facts don't entitle the claim to any compensation, or when the claim
    isn't logged with that same amount — there is nothing to pay, so no request is created.
    """
    eligibility = evaluate(args.disruption)
    if not eligibility.eligible or eligibility.compensation_eur == 0:
        raise ToolExecutionError(
            f"claim {args.claim_id} is not entitled to compensation (reasons: {', '.join(eligibility.reasons)}); "
            "no payment to issue"
        )
    ensure_claim_logged_for(args.claim_id, eligibility.compensation_eur, claims)
    request = approvals.submit(
        GuardedAction.ISSUE_PAYMENT,
        {
            "claim_id": args.claim_id,
            "amount_eur": eligibility.compensation_eur,
            "reasons": list(eligibility.reasons),
            "facts": args.disruption.model_dump(mode="json"),
        },
    )
    return IssuePaymentResult(
        approval_request_id=request.id, amount_eur=eligibility.compensation_eur, status=request.status
    )
