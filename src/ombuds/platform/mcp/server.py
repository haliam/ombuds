"""Standalone entrypoint: python -m ombuds.platform.mcp.server

Composition root (ADR-0003): the one place allowed to wire a feature's tool registry into `platform/mcp`.
Speaks MCP over stdio, so it can be launched directly by an MCP client (Claude Desktop, etc.) without a
running HTTP server.
"""

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ombuds import config
from ombuds.features.claims_triage.tools import build_tool_registry
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.guardrails.guarded_dispatcher import GuardedDispatcher
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.infrastructure.repositories import PostgresApprovalStore
from ombuds.platform.mcp.tool_bindings import build_mcp_server
from ombuds.platform.observability.logging import configure_logging


def build_server(registry: ToolRegistry) -> Server:
    """Build the MCP server over `registry`, with PII redacted from every call's arguments — external
    clients reach `search_kb` and the rest without passing through the agent (ADR-0013).
    """
    return build_mcp_server(GuardedDispatcher(registry), name="ombuds-claims-triage")


async def _run() -> None:
    # The same Postgres-backed approval store the API uses, so an approval submitted here is visible to `/approvals`.
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    try:
        server = build_server(build_tool_registry(PostgresApprovalStore(pool)))
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        pool.close()


def main() -> None:
    configure_logging()
    anyio.run(_run)


if __name__ == "__main__":
    main()
