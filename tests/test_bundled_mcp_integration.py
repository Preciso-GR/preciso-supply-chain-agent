import os

import pytest

from preciso_supply_agent.client import REQUIRED_TOOLS, PrecisoMCPClient


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_BUNDLED_MCP_INTEGRATION") != "1",
    reason="set RUN_BUNDLED_MCP_INTEGRATION=1 to exercise the local bundled MCP server",
)
async def test_bundled_mcp_discovers_required_tools() -> None:
    async with PrecisoMCPClient() as client:
        assert REQUIRED_TOOLS <= client.tool_names
        status = await client.call("get_server_status", {"workspace": "supply_chain"})
        assert status["graph"]["location"].endswith("data/preciso/supply_chain")
