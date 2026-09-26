"""TriageDecision: the structured shape the agent's final answer must validate against.

The model is prompted (see `platform/prompts/claims_triage/v3.txt`) to emit exactly this shape as JSON once
it has reached a verdict; `triage_use_case.py` validates its reply against it before returning.
"""

from pydantic import BaseModel, ConfigDict, Field


class TriageDecision(BaseModel):
    """The agent's final, structured verdict on one claim."""

    model_config = ConfigDict(frozen=True)

    eligible: bool
    compensation_amount_eur: float | None = Field(default=None, ge=0)
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)
    explanation: str = Field(min_length=1)
