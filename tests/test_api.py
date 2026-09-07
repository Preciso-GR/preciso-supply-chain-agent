from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import pytest

from preciso_supply_agent.api import create_app, load_local_env


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        return {"tool": tool_name, "arguments": arguments}


class FakeExtractor:
    configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        return {"provider": "test", "configured": True, "model": "test-model"}

    async def extract(self, documents, *, snapshot_effective_date, registry):
        self.calls.append(
            {
                "documents": documents,
                "snapshot_effective_date": snapshot_effective_date,
                "registry": registry,
            }
        )
        return {"status": "success", "payload": {"document_id": "extracted"}}

    async def answer(self, question, investigation):
        return {"status": "success", "answer": f"Grounded: {question}"}


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def app(fake_backend: FakeBackend):
    @asynccontextmanager
    async def factory() -> AsyncIterator[FakeBackend]:
        yield fake_backend

    return create_app(factory)


@pytest.fixture
def extraction_app(fake_backend: FakeBackend, tmp_path: Path):
    extractor = FakeExtractor()
    registry = {
        "entities": [
            {
                "canonical_id": "facility:arkon-components:northbridge",
                "entity_type": "FACILITY",
                "display_name": "Northbridge Fabrication Facility",
                "documented_aliases": [],
            }
        ],
        "ambiguous_aliases": [{"alias": "Plant 7", "status": "unresolved"}],
    }

    @asynccontextmanager
    async def factory() -> AsyncIterator[FakeBackend]:
        yield fake_backend

    return create_app(
        factory,
        extractor=extractor,
        registry=registry,
        artifact_dir=tmp_path / "extractions",
    ), extractor


async def request(app, method: str, url: str, **kwargs: Any) -> httpx.Response:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)


@pytest.mark.asyncio
async def test_api_routes_status_ingest_and_investigation(app: Any, fake_backend: FakeBackend) -> None:
    status = await request(app, "GET", "/api/status")
    ingest = await request(
        app,
        "POST",
        "/api/ingest",
        json={"approved": True, "payload": {"document_id": "reviewed"}},
    )
    investigation = await request(
        app,
        "POST",
        "/api/investigate",
        json={"facility_id": "facility:northbridge", "max_paths": 7},
    )

    assert status.status_code == 200
    assert ingest.status_code == 200
    assert investigation.status_code == 200
    assert fake_backend.calls == [
        ("get_server_status", {"workspace": "supply_chain"}),
        (
            "ingest_graph_tool",
            {"payload": {"document_id": "reviewed"}, "workspace": "supply_chain"},
        ),
        (
            "query_facility_unavailable",
            {
                "facility_id": "facility:northbridge",
                "max_paths": 7,
                "workspace": "supply_chain",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_requires_explicit_approval(app: Any, fake_backend: FakeBackend) -> None:
    response = await request(
        app,
        "POST",
        "/api/ingest",
        json={"approved": False, "payload": {"document_id": "not-reviewed"}},
    )

    assert response.status_code == 422
    assert fake_backend.calls == []


@pytest.mark.asyncio
async def test_investigation_get_route_and_bounds(app: Any, fake_backend: FakeBackend) -> None:
    response = await request(
        app,
        "GET",
        "/api/investigate?facility_id=facility:northbridge&max_paths=4",
    )
    assert response.status_code == 200
    assert fake_backend.calls[-1][1]["max_paths"] == 4

    invalid = await request(
        app,
        "POST",
        "/api/investigate",
        json={"facility_id": "facility:northbridge", "max_paths": 0},
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_extract_forwards_only_documents_date_and_server_registry(extraction_app: Any) -> None:
    app, extractor = extraction_app
    response = await request(
        app,
        "POST",
        "/api/extract",
        json={
            "snapshot_effective_date": "2026-01-15",
            "documents": [{"name": "facility.md", "content": "Northbridge manufactures C-17."}],
        },
    )
    assert response.status_code == 200
    assert extractor.calls[0]["snapshot_effective_date"] == "2026-01-15"
    assert extractor.calls[0]["documents"] == [
        {"name": "facility.md", "content": "Northbridge manufactures C-17."}
    ]
    assert response.json()["artifact"] == {
        "name": "preciso_extract.json",
        "url": "/api/extractions/preciso_extract.json",
        "description": "Exact Claude extraction payload awaiting or accepted by PRECISO.",
    }

    artifact = await request(app, "GET", "/api/extractions/preciso_extract.json")
    assert artifact.status_code == 200
    assert artifact.json() == {"document_id": "extracted"}


@pytest.mark.asyncio
async def test_provider_configuration_is_runtime_only_and_never_echoes_key(extraction_app: Any) -> None:
    app, _ = extraction_app
    response = await request(
        app,
        "POST",
        "/api/provider",
        json={
            "provider": "anthropic",
            "api_key": "local-secret",
            "model": "claude-sonnet-5",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["extractor"] == {
        "provider": "anthropic",
        "configured": True,
        "model": "claude-sonnet-5",
    }
    assert "local-secret" not in response.text


@pytest.mark.asyncio
async def test_grounded_answer_uses_the_configured_extractor(extraction_app: Any) -> None:
    app, _ = extraction_app
    response = await request(
        app,
        "POST",
        "/api/grounded-answer",
        json={"question": "Which products are exposed?", "investigation": {"status": "success"}},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Grounded: Which products are exposed?"


def test_local_env_loader_keeps_existing_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=from-file\n"
        "SUPPLY_CENTER_CLAUDE_MODEL='claude-sonnet-5'\n"
        "EMPTY_VALUE=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    monkeypatch.delenv("SUPPLY_CENTER_CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("EMPTY_VALUE", raising=False)

    load_local_env(env_file)

    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell"
    assert os.environ["SUPPLY_CENTER_CLAUDE_MODEL"] == "claude-sonnet-5"
    assert "EMPTY_VALUE" not in os.environ


@pytest.mark.asyncio
async def test_chat_resolves_facility_and_preserves_ambiguous_identity(extraction_app: Any, fake_backend: FakeBackend) -> None:
    app, _ = extraction_app
    resolved = await request(
        app,
        "POST",
        "/api/chat",
        json={"message": "What is exposed if Northbridge Fabrication Facility is unavailable?"},
    )
    ambiguous = await request(
        app,
        "POST",
        "/api/chat",
        json={"message": "What is exposed if Plant 7 is unavailable?"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["intent"] == "facility_unavailable"
    assert fake_backend.calls[-1][1]["facility_id"] == "facility:arkon-components:northbridge"
    assert ambiguous.json()["status"] == "ambiguous_identity"
