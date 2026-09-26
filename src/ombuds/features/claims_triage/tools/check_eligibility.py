"""Tool: check_eligibility. Read-only — dispatches to the airline vertical's EU261 rules, never computes them here."""

from ombuds.domain.models.claim import EligibilityResult
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.features.claims_triage.verticals.airline.rules import evaluate
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition

CHECK_ELIGIBILITY_TOOL = ToolDefinition(
    name="check_eligibility",
    description=(
        "Determine EU261 eligibility and compensation for a disrupted flight from its facts. "
        "Read-only: does not log or pay a claim."
    ),
    args_model=FlightDisruption,
)


def check_eligibility(args: FlightDisruption) -> EligibilityResult:
    """Evaluate EU261 eligibility and compensation for the given flight disruption facts."""
    return evaluate(args)
