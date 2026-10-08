"""Standalone entrypoint: python -m ombuds.platform.mcp.server

Composition root (ADR-0003): the one place allowed to wire a feature's tool registry into `platform/mcp`.
Speaks MCP over stdio, so it can be launched directly by an MCP client (Claude Desktop, etc.) without a
running HTTP server.
"""

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.guarded_dispatcher import GuardedDispatcher
from ombuds.platform.mcp.tool_bindings import build_mcp_server
from ombuds.platform.observability.logging import configure_logging


def build_server(registry: ToolRegistry | None = None) -> Server:
    """Build the MCP server over `registry` (default: the claims-triage tools), with PII redacted from every
    call's arguments — external clients reach `search_kb` and the rest without passing through the agent (ADR-0013).
    """
    return build_mcp_server(GuardedDispatcher(registry or build_tool_registry()), name="ombuds-claims-triage")


async def _run() -> None:
    server = build_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    configure_logging()
    anyio.run(_run)


if __name__ == "__main__":
    main()
