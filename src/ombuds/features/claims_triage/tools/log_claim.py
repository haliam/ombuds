"""Tool: log_claim. State-changing — every call must pass through the approval gate (non-negotiable, see AGENTS.md)."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.features.claims_triage.verticals.airline.rules import evaluate
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.guardrails.approval_gate import GuardedAction, check_approval


class LogClaimArgs(BaseModel):
    """Facts needed to log a claim decision. `disruption` is the same flight facts given to
    `check_eligibility` — never the model's own eligibility judgment, which `log_claim` recomputes itself
    (see AGENTS.md, ADR-0004, W1 review finding F-01)."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    disruption: FlightDisruption


class LogClaimResult(BaseModel):
    """Outcome of a log_claim attempt. `logged=False` covers both a denied approval and a future persistence failure."""

    model_config = ConfigDict(frozen=True)

    logged: bool
    reason: str


LOG_CLAIM_TOOL = ToolDefinition(
    name="log_claim",
    description=(
        "Record a claim's eligibility decision. State-changing: subject to human approval. "
        "Takes the flight facts, not an eligibility judgment — eligibility is recomputed independently."
    ),
    args_model=LogClaimArgs,
)


def log_claim(args: LogClaimArgs) -> LogClaimResult:
    """Attempt to log a claim decision.

    Recomputes eligibility from `args.disruption` via the rules engine itself — it never trusts a
    model-supplied eligibility judgment, so a hallucinated or manipulated `EligibilityResult` in the
    call's arguments can't reach persistence (see AGENTS.md, ADR-0004, W1 review finding F-01).

    Denied unconditionally while `approval_gate` is the deny-all stub (ADR-0004); persistence to the
    infrastructure layer is unreachable code until that gate is replaced in W2, so it isn't written yet.
    """
    eligibility = evaluate(args.disruption)
    decision = check_approval(GuardedAction.LOG_CLAIM)
    if not decision.approved:
        return LogClaimResult(logged=False, reason=decision.reason)
    raise ToolExecutionError(
        f"log_claim persistence not implemented (would log eligible={eligibility.eligible}, "
        f"compensation_eur={eligibility.compensation_eur}) — lands with the real approval gate in W2"
    )
