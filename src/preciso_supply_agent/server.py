"""Minimal standalone Supply-Chain MCP server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from preciso_supply_agent.core.engine import SupplyChainEngine
from preciso_supply_agent.tools.ingest import ingest_supply_chain as ingest_operation
from preciso_supply_agent.tools.investigate import investigate_facility as investigate_operation
from preciso_supply_agent.tools.status import get_supply_chain_status as status_operation


def default_database_path() -> Path:
    configured = os.getenv("PRECISO_SUPPLY_DB", "").strip()
    return Path(configured) if configured else Path("data/supply_chain.sqlite3")


def create_server(engine: SupplyChainEngine | None = None) -> FastMCP:
    runtime = engine
    server = FastMCP("preciso-supply-chain")

    def get_runtime() -> SupplyChainEngine:
        nonlocal runtime
        if runtime is None:
            runtime = SupplyChainEngine(default_database_path())
        return runtime

    @server.tool(
        name="get_supply_chain_status",
        description="Return readiness, snapshot, document commit states, and evidence graph counts.",
    )
    def get_supply_chain_status() -> dict[str, Any]:
        return status_operation(get_runtime())

    @server.tool(
        name="ingest_supply_chain",
        description="Validate and atomically commit a reviewed strict supply-chain extraction payload.",
    )
    def ingest_supply_chain(payload: dict[str, Any]) -> dict[str, Any]:
        return ingest_operation(get_runtime(), payload)

    @server.tool(
        name="investigate_facility",
        description=(
            "Return documented FACILITY->COMPONENT->PRODUCT exposure paths with evidence; "
            "fail closed when storage or evidence is incomplete."
        ),
    )
    def investigate_facility(facility_id: str, max_paths: int = 100) -> dict[str, Any]:
        return investigate_operation(get_runtime(), facility_id, max_paths=max_paths)

    return server


mcp = create_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
