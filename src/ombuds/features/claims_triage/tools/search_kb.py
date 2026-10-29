"""Tool: search_kb. Read-only — retrieves airline policy KB passages relevant to a query.

The single retrieval entry point (agent-loop review F-10): the agent decides when to look something up, and the
passages come back only as a tool result, never in the system prompt (F-06), so retrieved text can't
masquerade as instructions.
"""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.errors import ToolExecutionError
from ombuds.features.claims_triage.rag.retriever import Retriever
from ombuds.platform.ai.providers.base import ProviderUnavailableError
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition


class SearchKbArgs(BaseModel):
    """A query against the airline policy knowledge base."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class KbHit(BaseModel):
    """One retrieved passage, with enough provenance to cite it."""

    model_config = ConfigDict(frozen=True)

    source: str
    chunk_index: int
    snippet: str
    score: float


class SearchKbResult(BaseModel):
    """Passages retrieved for a `search_kb` query, most relevant first."""

    model_config = ConfigDict(frozen=True)

    hits: tuple[KbHit, ...]


SEARCH_KB_TOOL = ToolDefinition(
    name="search_kb",
    description="Search airline policy knowledge base passages relevant to a query. Read-only.",
    args_model=SearchKbArgs,
)


def search_kb(args: SearchKbArgs, retriever: Retriever) -> SearchKbResult:
    """Retrieve KB passages relevant to `args.query`; no hit above the relevance floor is an empty result.

    An unavailable embedding provider becomes a `ToolExecutionError`, so the agent sees an error result
    and can carry on (or escalate) instead of the whole triage run crashing.
    """
    try:
        citations = retriever.retrieve(args.query, args.top_k)
    except ProviderUnavailableError as exc:
        raise ToolExecutionError(f"knowledge base search is unavailable right now: {exc}") from exc
    return SearchKbResult(
        hits=tuple(
            KbHit(source=c.source, chunk_index=c.chunk_index, snippet=c.snippet, score=c.score) for c in citations
        )
    )
