"""Connects the LangGraph tool-calling loop to tools over a real MCP session, instead of an in-process
`ToolRegistry`.

Feature-agnostic (ADR-0003), like `tool_bindings.py`: this module only knows `mcp`'s own client types plus
the provider-agnostic `ToolCall`/`ToolDefinition`/`ToolResult` shapes from `platform/ai/`. It satisfies
`platform/ai/tool_loop.py`'s `ToolDispatcher` protocol, so `agent/graph.py` can be handed an `McpToolClient`
anywhere it currently takes a `ToolRegistry` — the graph's nodes stay synchronous either way.

`agent/graph.py`'s nodes are synchronous, but an MCP `ClientSession` is async-only. `McpToolClient` bridges
that with an `anyio` blocking portal: a background thread runs the session's event loop, and
`definitions()`/`dispatch_all()` submit work to it and block for the result.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Sequence
from contextlib import AbstractContextManager, asynccontextmanager
from types import TracebackType

import anyio.from_thread
import mcp.types as types
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel, ConfigDict

from ombuds.platform.ai.schemas.tool_calls import ToolCall, ToolDefinition, ToolResult


class _OpaqueArgs(BaseModel):
    """Placeholder `args_model` for a definition sourced from MCP: arguments are validated server-side
    (by the registry `platform/mcp/server.py` wraps), so the client has no local schema to validate
    against and doesn't need one — this only satisfies `ToolDefinition`'s required field."""

    model_config = ConfigDict(extra="allow")


def _to_tool_result(call: ToolCall, outcome: types.CallToolResult) -> ToolResult:
    text = "".join(block.text for block in outcome.content if isinstance(block, types.TextContent))
    return ToolResult(call_id=call.id, name=call.name, content=text, is_error=bool(outcome.isError))


@asynccontextmanager
async def _connect(params: StdioServerParameters) -> AsyncGenerator[ClientSession, None]:
    """Open the stdio transport and the session on top of it, and initialize, all as one nested async
    context manager — so `McpToolClient` can enter and exit both in the single task an `anyio` blocking
    portal keeps alive for it (see `wrap_async_context_manager`'s task-affinity requirement)."""
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


class McpToolClient:
    """Synchronous facade over an MCP `ClientSession` connected to a tool server subprocess.

    Defaults to launching `python -m ombuds.platform.mcp.server` (the composition root that serves the
    claims-triage tool catalogue), but any MCP stdio server command can be passed instead. Use as a
    context manager; `definitions()` and `dispatch_all()` are only valid once connected.
    """

    def __init__(
        self,
        command: str = sys.executable,
        args: Sequence[str] = ("-m", "ombuds.platform.mcp.server"),
    ) -> None:
        self._params = StdioServerParameters(command=command, args=list(args))
        self._portal_cm = anyio.from_thread.start_blocking_portal()
        self._session: ClientSession | None = None
        self._connection_cm: AbstractContextManager[ClientSession] | None = None

    def __enter__(self) -> McpToolClient:
        portal = self._portal_cm.__enter__()
        self._portal = portal
        self._connection_cm = portal.wrap_async_context_manager(_connect(self._params))
        self._session = self._connection_cm.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._connection_cm is not None
        self._connection_cm.__exit__(exc_type, exc, tb)
        self._portal_cm.__exit__(exc_type, exc, tb)
        self._session = None
        self._connection_cm = None

    def definitions(self) -> list[ToolDefinition]:
        """List the server's tools, converted to `ToolDefinition`s carrying its own JSON schema verbatim."""
        session = self._require_session()
        result = self._portal.call(session.list_tools)
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                args_model=_OpaqueArgs,
                raw_schema=tool.inputSchema,
            )
            for tool in result.tools
        ]

    def dispatch_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Dispatch every tool call from one provider turn, in order, over the MCP session."""
        session = self._require_session()

        async def _dispatch_all() -> list[ToolResult]:
            results = []
            for call in calls:
                outcome = await session.call_tool(call.name, call.arguments)
                results.append(_to_tool_result(call, outcome))
            return results

        return self._portal.call(_dispatch_all)

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("McpToolClient used outside its `with` block")
        return self._session
