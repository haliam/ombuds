"""Wraps a `ToolRegistry` for MCP exposure.

Feature-agnostic (ADR-0003): this module never imports from `features/`. It only knows the provider-
agnostic `ToolRegistry`/`ToolCall`/`ToolResult` shapes from `platform/ai/`. The composition root
(`server.py`) builds the registry from a feature (e.g. `claims_triage.tools.build_tool_registry()`) and
hands it to `build_mcp_server` here.
"""

import mcp.types as types
from mcp.server.lowlevel import Server

from ombuds.platform.ai.schemas.tool_calls import ToolCall
from ombuds.platform.ai.tool_loop import ToolRegistry


def build_mcp_server(registry: ToolRegistry, *, name: str = "ombuds") -> Server:
    """Build an MCP `Server` that lists and dispatches every tool in `registry`.

    Each tool's MCP input schema comes straight from its `ToolDefinition.args_model`, so the schema a
    client sees is exactly the schema `ToolRegistry.dispatch` validates against — no second definition
    to keep in sync.
    """
    server = Server(name)

    @server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=definition.name,
                description=definition.description,
                inputSchema=definition.input_schema(),
            )
            for definition in registry.definitions()
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> list[types.TextContent]:
        call = ToolCall(id=name, name=name, arguments=arguments)
        result = registry.dispatch(call)
        if result.is_error:
            raise RuntimeError(result.content)
        return [types.TextContent(type="text", text=result.content)]

    return server
