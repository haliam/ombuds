"""TriageDecision: the structured shape the agent's final answer must validate against.

The model is prompted (see `platform/prompts/claims_triage/v4.txt`) to emit exactly this shape as JSON once
it has reached a verdict; `triage_use_case.py` validates its reply against it, then verifies it against
`check_eligibility`'s own result (`verify_decision`, below) before returning it.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ombuds.domain.models.claim import EligibilityResult
from ombuds.platform.ai.schemas.structured_output import StructuredOutputError
from ombuds.platform.ai.schemas.tool_calls import ToolResult


class TriageDecision(BaseModel):
    """The agent's final, structured verdict on one claim."""

    model_config = ConfigDict(frozen=True)

    eligible: bool
    compensation_amount_eur: int | None = Field(default=None, ge=0)
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)
    explanation: str = Field(min_length=1)


def latest_eligibility_result(tool_results: Sequence[ToolResult]) -> EligibilityResult | None:
    """The most recent successful `check_eligibility` result in `tool_results`, or `None` if there isn't one.

    Only non-error results count: a failed call gave the model nothing to base a decision on. A malformed
    `content` (shouldn't happen — it's always `ToolRegistry.dispatch`'s own `model_dump_json()` output) is
    treated the same as no result, rather than raising, since that would be an internal bug, not something
    a repair prompt can help the model fix.
    """
    latest: EligibilityResult | None = None
    for result in tool_results:
        if result.name != "check_eligibility" or result.is_error:
            continue
        try:
            latest = EligibilityResult.model_validate_json(result.content)
        except ValidationError:
            continue
    return latest


def verify_decision(decision: TriageDecision, tool_results: Sequence[ToolResult]) -> None:
    """Verify `decision` against the latest `check_eligibility` result, raising `StructuredOutputError` if not.

    `parse_structured_output`/`TriageDecision` only checks that the model's reply has the *shape* of a
    verdict — this is the check that it's the *right* verdict: the LLM is never the source of truth for
    eligibility or the amount (see AGENTS.md, ADR-0004, foundations review finding F-01). Raising the same error
    type `triage_use_case.py` already repairs a malformed reply with means a content mismatch goes through
    that same repair loop, with the same `MAX_REPAIR_ATTEMPTS` budget, rather than needing a second one.
    """
    latest = latest_eligibility_result(tool_results)
    if latest is None:
        raise StructuredOutputError(
            "no successful check_eligibility result to verify this decision against — call check_eligibility "
            "with the flight facts before answering, and base eligible/compensation_amount_eur/reason_codes "
            "only on what it returns"
        )
    if decision.eligible != latest.eligible:
        raise StructuredOutputError(
            f"decision.eligible={decision.eligible} does not match check_eligibility's eligible={latest.eligible} "
            "— eligible must come from check_eligibility's result, not your own judgment"
        )
    actual_amount = decision.compensation_amount_eur or 0
    if actual_amount != latest.compensation_eur:
        raise StructuredOutputError(
            f"decision.compensation_amount_eur={decision.compensation_amount_eur} does not match "
            f"check_eligibility's compensation_eur={latest.compensation_eur}"
        )
    if tuple(decision.reason_codes) != tuple(latest.reasons):
        raise StructuredOutputError(
            f"decision.reason_codes={decision.reason_codes!r} does not match check_eligibility's "
            f"reasons={latest.reasons!r} — cite exactly the reason codes check_eligibility returned"
        )
