"""Tool: log_claim. State-changing — every call must pass through the approval gate (non-negotiable, see AGENTS.md)."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.models.claim import EligibilityResult
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.guardrails.approval_gate import GuardedAction, check_approval


class LogClaimArgs(BaseModel):
    """Facts needed to record a claim decision. `eligibility` is `check_eligibility`'s prior output, not recomputed."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    eligibility: EligibilityResult


class LogClaimResult(BaseModel):
    """Outcome of a log_claim attempt. `logged=False` covers both a denied approval and a future persistence failure."""

    model_config = ConfigDict(frozen=True)

    logged: bool
    reason: str


LOG_CLAIM_TOOL = ToolDefinition(
    name="log_claim",
    description="Record a claim's eligibility decision. State-changing: subject to human approval.",
    args_model=LogClaimArgs,
)


def log_claim(args: LogClaimArgs) -> LogClaimResult:
    """Attempt to log a claim decision.

    Denied unconditionally while `approval_gate` is the deny-all stub (ADR-0004); persistence to the
    infrastructure layer is unreachable code until that gate is replaced in W2, so it isn't written yet.
    """
    decision = check_approval(GuardedAction.LOG_CLAIM)
    if not decision.approved:
        return LogClaimResult(logged=False, reason=decision.reason)
    raise NotImplementedError("log_claim persistence lands with the real approval gate in W2")
