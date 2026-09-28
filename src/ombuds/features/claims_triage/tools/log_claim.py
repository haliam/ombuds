"""Tool: log_claim. State-changing — only ever *submits* an approval request, never executes (ADR-0009)."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.features.claims_triage.verticals.airline.rules import evaluate
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.guardrails.approval_gate import ApprovalStatus, GuardedAction, submit_for_approval


class LogClaimArgs(BaseModel):
    """Facts needed to log a claim decision. `disruption` is the same flight facts given to
    `check_eligibility` — never the model's own eligibility judgment, which `log_claim` recomputes itself
    (see AGENTS.md, ADR-0004, W1 review finding F-01). In a triage run, `claim_id` is overwritten with the
    run's server-issued id before this tool sees it (`tools.scope_for_agent`, ADR-0009)."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    disruption: FlightDisruption


class LogClaimResult(BaseModel):
    """Outcome of a log_claim call: the approval request it submitted, and that request's current status."""

    model_config = ConfigDict(frozen=True)

    approval_request_id: str
    status: ApprovalStatus
    reason: str


LOG_CLAIM_TOOL = ToolDefinition(
    name="log_claim",
    description=(
        "Record a claim's eligibility decision. State-changing: submits the decision for human approval "
        "rather than recording it immediately. Takes the flight facts, not an eligibility judgment — "
        "eligibility is recomputed independently."
    ),
    args_model=LogClaimArgs,
)

_STATUS_REASONS = {
    ApprovalStatus.PENDING: "submitted for human approval; it will be recorded once approved",
    ApprovalStatus.APPROVED: "approved by a human; it will be recorded shortly",
    ApprovalStatus.DENIED: "a human reviewer denied recording this decision",
    ApprovalStatus.EXECUTED: "already recorded",
}


def log_claim(args: LogClaimArgs) -> LogClaimResult:
    """Submit a claim decision for human approval.

    Recomputes eligibility from `args.disruption` via the rules engine itself — it never trusts a
    model-supplied eligibility judgment (see AGENTS.md, ADR-0004, W1 review finding F-01). The approval
    payload is exactly what the human approves and what will be executed once approved: the `claim_id`, the
    rules-derived outcome, and the flight facts it was derived from — so different facts are a different
    request. Re-submitting identical facts returns the existing request, whatever its status (ADR-0009).
    """
    eligibility = evaluate(args.disruption)
    request = submit_for_approval(
        GuardedAction.LOG_CLAIM,
        {
            "claim_id": args.claim_id,
            "eligible": eligibility.eligible,
            "compensation_eur": eligibility.compensation_eur,
            "reasons": list(eligibility.reasons),
            "facts": args.disruption.model_dump(mode="json"),
        },
    )
    return LogClaimResult(
        approval_request_id=request.id,
        status=request.status,
        reason=_STATUS_REASONS[request.status],
    )
