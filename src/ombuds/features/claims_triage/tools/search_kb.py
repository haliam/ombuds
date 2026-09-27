"""Tool: search_kb. Read-only — retrieves airline policy KB passages relevant to a query.

Retrieval isn't implemented yet: `features/claims_triage/rag/retriever.py` is still a stub (chunking,
embeddings and ingest land with the RAG work). This tool exists so the agent and MCP clients can bind
against its schema now; it raises `ToolExecutionError` rather than returning fabricated hits.
"""

from pydantic import BaseModel, ConfigDict, Field

from ombuds.domain.errors import ToolExecutionError
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
    snippet: str


class SearchKbResult(BaseModel):
    """Passages retrieved for a `search_kb` query, most relevant first."""

    model_config = ConfigDict(frozen=True)

    hits: tuple[KbHit, ...]


SEARCH_KB_TOOL = ToolDefinition(
    name="search_kb",
    description="Search airline policy knowledge base passages relevant to a query. Read-only.",
    args_model=SearchKbArgs,
)


def search_kb(args: SearchKbArgs) -> SearchKbResult:
    """Retrieve KB passages relevant to `args.query`.

    Always raises: the retriever behind this tool (`rag/retriever.py`) hasn't been built yet, so there
    is no real index to search. Raising here keeps that gap visible instead of returning empty or
    fabricated hits that would look like a working retrieval path.
    """
    raise ToolExecutionError(
        f"search_kb retrieval not implemented yet (query={args.query!r}) — rag/retriever.py is still a stub"
    )
