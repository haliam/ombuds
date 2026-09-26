"""API schemas: request/response bodies for the claims-triage routes."""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.platform.ai.schemas.tool_calls import ToolResult


class TriageRequest(BaseModel):
    """A passenger's claim, in their own words."""

    model_config = ConfigDict(frozen=True)

    claim_text: str = Field(min_length=1)


class TriageResponse(BaseModel):
    """The agent's answer plus every tool call it made while reaching it, for auditability."""

    model_config = ConfigDict(frozen=True)

    answer: str
    tool_results: tuple[ToolResult, ...]
