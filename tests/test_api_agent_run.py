from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from preciso_supply_agent.api import create_app


class Backend:
    def __init__(self, *, invalid_once: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.validation_calls = 0
        self.invalid_once = invalid_once

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "get_server_status":
            return {"overall": "ready", "warnings": []}
        if name == "validate_extraction":
            self.validation_calls += 1
            if self.invalid_once and self.validation_calls == 1:
                return {"status": "invalid", "errors": ["relationship endpoint is missing"]}
            return {"status": "success", "valid": True}
        if name == "ingest_from_file":
            return {"status": "success"}
        if name == "query_graph_tool":
            return {"status": "success", "raw_data": {"text_chunks": [{"chunk_id": "a"}]}}
        raise AssertionError(name)


class Extractor:
    configured = True

    def __init__(self) -> None:
        self.repair_errors: list[list[str]] = []

    def status(self) -> dict[str, Any]:
        return {"provider": "test", "configured": True, "model": "test"}

    async def extract_document(self, document: dict[str, Any], **_: Any) -> dict[str, Any]:
        chunk = f"{document['name']}#chunk_001"
        return {
            "payload": {
                "chunks": [{"chunk_id": chunk, "content": document["content"]}],
                "entities": [],
                "relationships": [
                    {
                        "src_id": "company:source",
                        "tgt_id": "component:source:item",
                        "keywords": "MANUFACTURES",
                    }
                ],
            }
        }

    async def repair_document(
        self,
        document: dict[str, Any],
        extraction: dict[str, Any],
        errors: list[str],
        **_: Any,
    ) -> dict[str, Any]:
        self.repair_errors.append(errors)
        return {
            "patch": {
                "operation": "replace_relationship",
                "match": {
                    "src_id": "company:source",
                    "tgt_id": "component:source:item",
                    "keywords": "MANUFACTURES",
                },
                "replacement": {"src_id": "facility:source:plant"},
            }
        }

    async def answer(self, question: str, _: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success", "answer": f"Answer: {question}"}


async def request(app: Any, method: str, url: str, **kwargs: Any) -> httpx.Response:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)


async def wait_for_run(app: Any, run_id: str) -> None:
    run = app.state.agent_runtime.run_for_id(run_id)
    assert run.task is not None
    await asyncio.wait_for(run.task, timeout=2)


@pytest.mark.asyncio
async def test_api_runs_return_before_live_execution_and_resume(tmp_path: Path) -> None:
    backend = Backend()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Backend]:
        yield backend

    app = create_app(factory, extractor=Extractor(), registry={"entities": []}, artifact_dir=tmp_path / "extractions")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post(
                "/api/runs",
                json={"message": "What is connected?", "documents": [{"name": "source.md", "content": "fact"}]},
            )
            body = started.json()
            assert started.status_code == 200
            assert body["status"] == "running"
            await wait_for_run(app, body["run_id"])
            paused = (await client.get(f"/api/runs/{body['thread_id']}")).json()
            assert paused["status"] == "awaiting_approval"
            assert not any(name == "ingest_from_file" for name, _ in backend.calls)
            assert len(paused["state"]["extraction_results"]) == 1
            resumed = await client.post(f"/api/runs/{body['thread_id']}/approval", json={"approved": True})
            assert resumed.json()["status"] == "running"
            await wait_for_run(app, body["run_id"])
    assert [name for name, _ in backend.calls].count("ingest_from_file") == 1
    assert [name for name, _ in backend.calls].count("query_graph_tool") == 1


@pytest.mark.asyncio
async def test_api_streams_surgical_repair_events(tmp_path: Path) -> None:
    backend = Backend(invalid_once=True)
    extractor = Extractor()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Backend]:
        yield backend

    app = create_app(factory, extractor=extractor, registry={"entities": []}, artifact_dir=tmp_path / "extractions")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post(
                "/api/runs",
                json={"message": "What is connected?", "documents": [{"name": "source.md", "content": "fact"}]},
            )
            body = started.json()
            await wait_for_run(app, body["run_id"])
            assert extractor.repair_errors == [["relationship endpoint is missing"]]
            events = [event async for event in app.state.agent_runtime.events(body["run_id"])]
    for event_type in (
        "extraction.validation_failed",
        "extraction.repair.started",
        "extraction.patch.generated",
        "extraction.edit.started",
        "extraction.edit.completed",
        "extraction.revalidation.started",
        "extraction.revalidation.completed",
    ):
        assert any(event["type"] == event_type for event in events)


@pytest.mark.asyncio
async def test_api_extraction_instruction_finishes_without_graph_query(tmp_path: Path) -> None:
    backend = Backend()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Backend]:
        yield backend

    app = create_app(factory, extractor=Extractor(), registry={"entities": []}, artifact_dir=tmp_path / "extractions")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post(
                "/api/runs",
                json={
                    "message": "Extract these documents and prepare them for review.",
                    "documents": [{"name": "source.md", "content": "fact"}],
                },
            )
            first = started.json()
            await wait_for_run(app, first["run_id"])
            await client.post(f"/api/runs/{first['thread_id']}/approval", json={"approved": True})
            await wait_for_run(app, first["run_id"])
            body = (await client.get(f"/api/runs/{first['thread_id']}")).json()
    assert body["intent"] == "new_sources"
    assert body["answer"] == (
        "The source artifacts were approved and ingested into PRECISO; "
        "no graph question was requested."
    )
    assert not any(name == "query_graph_tool" for name, _ in backend.calls)


@pytest.mark.asyncio
async def test_rejection_resumes_the_checkpoint_without_ingestion(tmp_path: Path) -> None:
    backend = Backend()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Backend]:
        yield backend

    app = create_app(factory, extractor=Extractor(), registry={"entities": []}, artifact_dir=tmp_path / "extractions")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post(
                "/api/runs",
                json={"message": "Build the graph", "documents": [{"name": "source.md", "content": "fact"}]},
            )
            run = started.json()
            await wait_for_run(app, run["run_id"])
            rejected = await client.post(f"/api/runs/{run['thread_id']}/approval", json={"approved": False})
            assert rejected.json()["run_id"] == run["run_id"]
            await wait_for_run(app, run["run_id"])

    assert not any(name == "ingest_from_file" for name, _ in backend.calls)
