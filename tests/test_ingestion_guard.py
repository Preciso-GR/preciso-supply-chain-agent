from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from preciso_supply_agent.api import create_app


class Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {"overall": "ready"}


@pytest.mark.asyncio
async def test_legacy_ingest_route_is_not_available() -> None:
    backend = Backend()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Backend]:
        yield backend

    app = create_app(factory, registry={"entities": []})
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/ingest", json={"approved": True, "payload": {"document_id": "x"}}
            )

    assert response.status_code == 404
    assert not backend.calls
