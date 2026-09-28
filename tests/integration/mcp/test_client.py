"""Real MCP round-trip: `McpToolClient` against the actual `platform/mcp/server.py` subprocess.

Unlike `tests/unit/platform/mcp/test_tool_bindings.py` (which drives `build_mcp_server` in-process), this
spawns the standalone server the same way a real MCP client would, over stdio.
"""

from ombuds.platform.mcp.client import McpToolClient


def test_definitions_lists_the_claims_triage_tool_catalogue() -> None:
    with McpToolClient() as client:
        names = {definition.name for definition in client.definitions()}

    assert names == {"search_kb", "check_eligibility", "log_claim", "issue_payment"}


def test_dispatch_all_runs_check_eligibility_over_the_mcp_session() -> None:
    from ombuds.platform.ai.schemas.tool_calls import ToolCall

    call = ToolCall(
        id="call-1",
        name="check_eligibility",
        arguments={
            "disruption": "cancellation",
            "distance_km": 1200,
            "intra_eu": True,
            "departs_from_eu": True,
            "arrives_in_eu": True,
            "eu_carrier": True,
        },
    )

    with McpToolClient() as client:
        results = client.dispatch_all([call])

    assert len(results) == 1
    assert results[0].name == "check_eligibility"
    assert results[0].is_error is False
    assert "eligible" in results[0].content


def test_dispatch_all_reports_an_unknown_tool_as_an_error_result() -> None:
    from ombuds.platform.ai.schemas.tool_calls import ToolCall

    call = ToolCall(id="call-1", name="nonexistent", arguments={})

    with McpToolClient() as client:
        results = client.dispatch_all([call])

    assert results[0].is_error is True


def test_a_failed_connect_does_not_leak_the_portal_thread() -> None:
    import threading

    import pytest

    before = threading.active_count()

    with pytest.raises(OSError), McpToolClient(command="/nonexistent/ombuds-mcp-server"):
        pass

    assert threading.active_count() == before
