from __future__ import annotations

import pytest

from preciso_supply_agent import SupplyChainApplication


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool_name: str, arguments: dict) -> dict:
        self.calls.append((tool_name, arguments))
        return {"status": "success"}


@pytest.mark.asyncio
async def test_application_routes_to_preciso_supply_chain_tools():
    backend = FakeBackend()
    app = SupplyChainApplication(backend)
    await app.status()
    await app.ingest_reviewed_extraction({"document_id": "reviewed"})
    await app.investigate_facility("facility:arkon-components:northbridge", max_paths=7)
    assert backend.calls == [
        ("get_server_status", {"workspace": "supply_chain"}),
        ("ingest_graph_tool", {"payload": {"document_id": "reviewed"}, "workspace": "supply_chain"}),
        ("query_facility_unavailable", {"facility_id": "facility:arkon-components:northbridge", "max_paths": 7, "workspace": "supply_chain"}),
    ]
