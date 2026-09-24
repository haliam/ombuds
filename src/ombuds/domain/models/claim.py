"""Claim, EligibilityResult, ProposedAction"""

from pydantic import BaseModel, ConfigDict, Field


class EligibilityResult(BaseModel):
    """Outcome of a deterministic eligibility check. Vertical-agnostic: reasons are codes a vertical defines."""

    model_config = ConfigDict(frozen=True)

    eligible: bool
    compensation_eur: int = Field(ge=0)
    reasons: tuple[str, ...] = Field(description="Machine-readable codes explaining the outcome, in evaluation order")
