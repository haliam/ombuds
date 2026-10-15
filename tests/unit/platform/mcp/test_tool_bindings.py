import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from ombuds.features.claims_triage.rag.retriever import Retriever
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.guardrails.approval_gate import ApprovalGate
from ombuds.platform.infrastructure.vector_store import PgVectorStore
from ombuds.platform.mcp.tool_bindings import build_mcp_server
from tests.fakes import DownEmbedder, InMemoryClaims


@pytest.fixture
def registry():
    # search_kb's embedding provider is down, so the one tool call that needs it fails predictably.
    return build_tool_registry(ApprovalGate(), InMemoryClaims(), lambda: Retriever(DownEmbedder(), PgVectorStore(None)))  # type: ignore[arg-type]


async def test_list_tools_exposes_all_four_claims_triage_tools(registry) -> None:
    server = build_mcp_server(registry)

    async with create_connected_server_and_client_session(server) as session:
        result = await session.list_tools()

    assert {tool.name for tool in result.tools} == {
        "search_kb",
        "check_eligibility",
        "log_claim",
        "issue_payment",
    }


async def test_call_tool_dispatches_to_the_registry_and_returns_its_result(registry) -> None:
    server = build_mcp_server(registry)

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "check_eligibility",
            {
                "disruption": "cancellation",
                "distance_km": 1200,
                "intra_eu": True,
                "departs_from_eu": True,
                "arrives_in_eu": True,
                "eu_carrier": True,
            },
        )

    assert result.isError is False
    content = result.content[0]
    assert isinstance(content, TextContent)
    assert '"eligible":true' in content.text


async def test_call_tool_surfaces_a_tool_execution_error_as_an_error_result(registry) -> None:
    server = build_mcp_server(registry)

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("search_kb", {"query": "baggage delay"})

    assert result.isError is True
    content = result.content[0]
    assert isinstance(content, TextContent)
    assert "unavailable" in content.text
