"""Standalone entrypoint: python -m ombuds.platform.mcp.server

Composition root (ADR-0003): the one place allowed to wire a feature's tool registry into `platform/mcp`.
Speaks MCP over stdio, so it can be launched directly by an MCP client (Claude Desktop, etc.) without a
running HTTP server.
"""

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ombuds import config
from ombuds.features.claims_triage.application.runtime import build_runtime
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.guarded_dispatcher import GuardedDispatcher
from ombuds.platform.guardrails.policy_engine import OpaHttpPolicyEngine
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.mcp.tool_bindings import build_mcp_server
from ombuds.platform.observability.logging import configure_logging
from ombuds.platform.observability.tracing import configure_tracing


def build_server(registry: ToolDispatcher) -> Server:
    """Build the MCP server over `registry`, with PII redacted from every call's arguments — external
    clients reach `search_kb` and the rest without passing through the agent (ADR-0013).
    """
    return build_mcp_server(GuardedDispatcher(registry), name="ombuds-claims-triage")


async def _run() -> None:
    # The same Postgres-backed runtime the API uses, so an approval submitted here is visible to `/approvals`.
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    try:
        engine = OpaHttpPolicyEngine(config.OPA_URL, config.OPA_TIMEOUT_SECONDS)
        server = build_server(build_runtime(pool, engine, config.PAYOUT_LIMIT_EUR).registry)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        pool.close()


def main() -> None:
    configure_logging()
    configure_tracing(config.OTEL_TRACES_EXPORTER)
    anyio.run(_run)


if __name__ == "__main__":
    main()
