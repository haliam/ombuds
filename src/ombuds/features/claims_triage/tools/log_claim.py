"""Tool: log_claim. State-changing — every call must pass through the approval gate (non-negotiable, see AGENTS.md)."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.errors import ToolExecutionError
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

    Denied unconditionally while `approval_gate` is the deny-all stub (ADR-0004). The approved branch is
    unreachable while that stub is in place; once persistence lands with the real approval gate in W2,
    a failure there should raise `ToolExecutionError` too, so it surfaces to the model as a tool error
    rather than crashing the triage turn (see `ToolRegistry.dispatch`).
    """
    decision = check_approval(GuardedAction.LOG_CLAIM)
    if not decision.approved:
        return LogClaimResult(logged=False, reason=decision.reason)
    raise ToolExecutionError("log_claim persistence not implemented — lands with the real approval gate in W2")
