"""Standalone entrypoint: python -m ombuds.platform.mcp.server

Composition root (ADR-0003): the one place allowed to wire a feature's tool registry into `platform/mcp`.
Speaks MCP over stdio, so it can be launched directly by an MCP client (Claude Desktop, etc.) without a
running HTTP server.
"""

import anyio
from mcp.server.stdio import stdio_server

from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.mcp.tool_bindings import build_mcp_server


async def _run() -> None:
    registry = build_tool_registry()
    server = build_mcp_server(registry, name="ombuds-claims-triage")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    main()
