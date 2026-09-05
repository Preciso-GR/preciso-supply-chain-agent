from __future__ import annotations

import pytest

from preciso_supply_agent.server import create_server


@pytest.mark.asyncio
async def test_mcp_exposes_only_the_three_initial_tools(engine):
    server = create_server(engine)

    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "get_supply_chain_status",
        "ingest_supply_chain",
        "investigate_facility",
    }


@pytest.mark.asyncio
async def test_mcp_calls_cross_the_real_engine_boundary(engine, payload):
    server = create_server(engine)

    ingest_result = await server.call_tool("ingest_supply_chain", {"payload": payload})
    query_result = await server.call_tool(
        "investigate_facility",
        {"facility_id": "facility:arkon-components:northbridge", "max_paths": 100},
    )

    assert ingest_result[0][0].text
    assert ingest_result[1]["status"] == "success"
    assert query_result[0][0].text
    assert query_result[1]["status"] == "success"
    assert engine.status()["readiness"] is True


def test_runtime_source_has_no_preciso_graphrag_imports():
    from pathlib import Path

    source_root = Path(__file__).resolve().parents[1] / "src"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))
    assert "preciso-graphrag" not in combined
    assert "preciso_graphrag" not in combined
    assert "sys.path" not in combined
