from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import BaseModel

from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.tool_loop import ToolRegistry
from ombuds.platform.mcp.server import build_server


class _QueryArgs(BaseModel):
    query: str


async def test_the_server_redacts_pii_from_an_external_clients_tool_arguments() -> None:
    received: list[str] = []

    def handler(args: BaseModel) -> BaseModel:
        assert isinstance(args, _QueryArgs)
        received.append(args.query)
        return args

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="search_kb", description="d", args_model=_QueryArgs), handler)

    async with create_connected_server_and_client_session(build_server(registry)) as session:
        result = await session.call_tool("search_kb", {"query": "refund for jane.doe@example.com"})

    assert result.isError is False
    assert received == ["refund for [EMAIL]"]
