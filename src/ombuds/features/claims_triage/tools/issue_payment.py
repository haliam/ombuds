"""Tool: issue_payment. State-changing — every call must pass through the approval gate (non-negotiable, see AGENTS.md)."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.errors import ToolExecutionError
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.guardrails.approval_gate import GuardedAction, check_approval


class IssuePaymentArgs(BaseModel):
    """A payment to disburse for an already-logged claim."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    amount_eur: int = Field(gt=0)


class IssuePaymentResult(BaseModel):
    """Outcome of an issue_payment attempt. `issued=False` covers both a denied approval and a future
    disbursement failure."""

    model_config = ConfigDict(frozen=True)

    issued: bool
    reason: str


ISSUE_PAYMENT_TOOL = ToolDefinition(
    name="issue_payment",
    description=(
        "Disburse compensation for a logged claim. State-changing: subject to human approval and the "
        "payout policy engine."
    ),
    args_model=IssuePaymentArgs,
)


def issue_payment(args: IssuePaymentArgs) -> IssuePaymentResult:
    """Attempt to issue payment for `args.claim_id`.

    Denied unconditionally while `approval_gate` is the deny-all stub (ADR-0004); disbursement to a real
    payment provider is unreachable code until that gate is replaced in W2, so it isn't written yet
    (mirrors `log_claim`'s stub, see AGENTS.md).
    """
    decision = check_approval(GuardedAction.ISSUE_PAYMENT)
    if not decision.approved:
        return IssuePaymentResult(issued=False, reason=decision.reason)
    raise ToolExecutionError(
        f"issue_payment disbursement not implemented (would pay claim_id={args.claim_id}, "
        f"amount_eur={args.amount_eur}) — lands with the real approval gate and payment provider in W2"
    )
