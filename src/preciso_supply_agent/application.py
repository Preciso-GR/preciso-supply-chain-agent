"""Application boundary over the authoritative Preciso MCP tools."""

from __future__ import annotations

from typing import Any, Protocol


class SupplyChainBackend(Protocol):
    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class SupplyChainApplication:
    """Routes analyst workflows to Preciso without reimplementing domain logic."""

    def __init__(self, backend: SupplyChainBackend):
        self.backend = backend

    async def status(self) -> dict[str, Any]:
        return await self.backend.call("get_server_status", {"workspace": "supply_chain"})

    async def ingest_reviewed_extraction(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.backend.call(
            "ingest_graph_tool", {"payload": payload, "workspace": "supply_chain"}
        )

    async def investigate_facility(
        self, facility_id: str, *, max_paths: int = 100
    ) -> dict[str, Any]:
        return await self.backend.call(
            "query_facility_unavailable",
            {
                "facility_id": facility_id,
                "max_paths": max_paths,
                "workspace": "supply_chain",
            },
        )
