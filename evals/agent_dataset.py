"""Agent eval dataset: claims in the passenger's words, with the outcome the agent should reach.

A `decision` case carries the flight facts a careful reader would extract from the text. The expected verdict is
not stored: it is computed from those facts by the rules engine, so it cannot drift from `rules.py` and what the
eval measures is whether the agent extracts the facts, not whether it can do the arithmetic.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from ombuds.domain.models.claim import EligibilityResult
from ombuds.features.claims_triage.verticals.airline.evidence_schema import FlightDisruption
from ombuds.features.claims_triage.verticals.airline.rules import evaluate

AGENT_DATASET = Path(__file__).parent / "datasets" / "airline_claims.jsonl"

Outcome = Literal["decision", "clarify", "escalate"]


class AgentCase(BaseModel):
    """One claim and how the run should end: a verified decision, a question to the passenger, or an escalation."""

    model_config = ConfigDict(frozen=True)

    id: str
    claim: str
    outcome: Outcome
    facts: FlightDisruption | None = None

    @model_validator(mode="after")
    def _facts_only_for_decisions(self) -> "AgentCase":
        if (self.outcome == "decision") != (self.facts is not None):
            raise ValueError(f"{self.id}: decision cases need facts, clarify and escalate cases must have none")
        return self

    def expected(self) -> EligibilityResult | None:
        """The rules engine's verdict on this case's facts, or `None` when the case is not a decision."""
        return None if self.facts is None else evaluate(self.facts)


def load_cases(path: Path = AGENT_DATASET) -> list[AgentCase]:
    """Read the JSONL dataset, rejecting duplicate ids."""
    cases = [AgentCase.model_validate(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in the agent eval dataset")
    return cases
