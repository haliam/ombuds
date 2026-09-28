"""API schemas: request/response bodies for the claims-triage routes."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.features.claims_triage.application.decision import TriageDecision
from ombuds.platform.ai.schemas.tool_calls import ToolResult

MAX_CLAIM_TEXT_CHARS = 10_000


class TriageRequest(BaseModel):
    """A passenger's claim, in their own words. Capped so one request can't run up unbounded token cost."""

    model_config = ConfigDict(frozen=True)

    claim_text: str = Field(min_length=1, max_length=MAX_CLAIM_TEXT_CHARS)


class TriageResponse(BaseModel):
    """The agent's answer plus every tool call it made while reaching it, for auditability.

    `escalated` is `True` when the agent couldn't reach a verified decision on its own and the run was
    handed to `agent/nodes/escalate_retry.py` instead — see `TriageResult` for what that means for
    `decision`/`answer`. Callers should route an escalated claim to a human rather than treat `answer`
    as a verdict.
    """

    model_config = ConfigDict(frozen=True)

    claim_id: str
    answer: str
    decision: TriageDecision | None
    tool_results: tuple[ToolResult, ...]
    escalated: bool = False
    escalation_reason: str | None = None
