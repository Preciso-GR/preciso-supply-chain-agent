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

    async def validate_extraction(self, file_path: str) -> dict[str, Any]:
        """Delegate structural validation to PRECISO; do not mirror its rules here."""
        return await self.backend.call(
            "validate_extraction",
            {"file_path": file_path, "workspace": "supply_chain"},
        )

    async def ingest_extraction_file(self, file_path: str) -> dict[str, Any]:
        """Ingest one reviewed artifact through PRECISO's additive file tool."""
        return await self.backend.call(
            "ingest_from_file",
            {"file_path": file_path, "workspace": "supply_chain"},
        )

    async def query_graph(self, query: str, *, mode: str = "mix") -> dict[str, Any]:
        """Return PRECISO's graph and evidence context without local retrieval."""
        return await self.backend.call(
            "query_graph_tool",
            {"query": query, "mode": mode, "workspace": "supply_chain"},
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
