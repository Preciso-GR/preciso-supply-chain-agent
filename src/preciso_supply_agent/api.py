"""FastAPI adapter for the SUPPLY CENTER frontend.

This module is intentionally a thin HTTP boundary.  The configured Preciso
MCP server remains responsible for validation, persistence, and dependency
traversal; this API only enforces the frontend request envelope and forwards
the existing application contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, ConfigDict, Field, field_validator

from preciso_supply_agent.agent.artifacts import ExtractionArtifactStore
from preciso_supply_agent.agent.graph import AgentDependencies
from preciso_supply_agent.agent.runtime import RunSnapshot, SupplyAgentRuntime
from preciso_supply_agent.application import SupplyChainApplication, SupplyChainBackend
from preciso_supply_agent.client import PrecisoMCPClient, PrecisoMCPConfig
from preciso_supply_agent.documents.store import SourceStore
from preciso_supply_agent.extraction import ClaudeExtractor, ExtractionError, load_registry
from preciso_supply_agent.intent import resolve_chat_intent

MAX_PATHS = 1000
MAX_DOCUMENTS = 8
MAX_DOCUMENT_CHARACTERS = 250_000
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_ARTIFACT_DIR = REPOSITORY_ROOT / ".runtime" / "extractions"
DEFAULT_UPLOAD_DIR = REPOSITORY_ROOT / "uploads"
EXTRACTION_ARTIFACT_NAME = "preciso_extract.json"


def load_local_env(path: Path = REPOSITORY_ROOT / ".env") -> None:
    """Load simple KEY=VALUE lines for local development without a dependency."""

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


class FacilityInvestigationRequest(BaseModel):
    """Facility query request used by the chat workspace."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str = Field(min_length=1)
    max_paths: int = Field(default=100, ge=1, le=MAX_PATHS)


class SourceDocument(BaseModel):
    """Text-based document sent from the local browser workspace."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARACTERS)

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        cleaned = value.strip()
        if Path(cleaned).name != cleaned:
            raise ValueError("document name must not contain a path")
        return cleaned


class ExtractionRequest(BaseModel):
    """Fresh extraction input; never accepts gold relationships or expected paths."""

    model_config = ConfigDict(extra="forbid")

    snapshot_effective_date: date
    documents: list[SourceDocument] = Field(min_length=1, max_length=MAX_DOCUMENTS)


class ProviderConfigurationRequest(BaseModel):
    """Runtime LLM provider configuration for the local API process.

    The key is intentionally accepted only by the local FastAPI process and is
    never returned to the browser or written to disk.
    """

    model_config = ConfigDict(extra="forbid")

    provider: Literal["anthropic"]
    api_key: str = Field(min_length=1, max_length=4000)
    model: str = Field(default="claude-sonnet-5", min_length=1, max_length=120)

    @field_validator("api_key", "model", mode="before")
    @classmethod
    def strip_secret_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ChatRequest(BaseModel):
    """Natural-language entrypoint for the supported deterministic scenario."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    max_paths: int = Field(default=100, ge=1, le=MAX_PATHS)


class GroundedAnswerRequest(BaseModel):
    """Question plus an authoritative PRECISO investigation result."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    investigation: dict[str, Any]


class AgentRunRequest(BaseModel):
    """A chat turn submitted to the stateful LangGraph runtime."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=160)
    snapshot_effective_date: date = Field(default_factory=date.today)
    documents: list[SourceDocument] | None = Field(default=None, max_length=MAX_DOCUMENTS)
    source_ids: list[str] | None = Field(default=None, max_length=MAX_DOCUMENTS)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class Extractor(Protocol):
    configured: bool

    def status(self) -> dict[str, Any]: ...

    async def extract(
        self,
        documents: list[dict[str, str]],
        *,
        snapshot_effective_date: str,
        registry: dict[str, Any],
    ) -> dict[str, Any]: ...


class ExtractorProxy:
    """Lets a long-lived graph see provider changes made through /api/provider."""

    def __init__(self, getter: Callable[[], Extractor]):
        self._getter = getter

    @property
    def configured(self) -> bool:
        return self._getter().configured

    def status(self) -> dict[str, Any]:
        return self._getter().status()

    async def extract_document(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        extractor = self._getter()
        method = getattr(extractor, "extract_document", None)
        if method is not None:
            return await method(*args, **kwargs)
        return await extractor.extract([args[0]], **{key: kwargs[key] for key in kwargs})

    async def repair_document(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        method = getattr(self._getter(), "repair_document", None)
        if method is None:
            raise ExtractionError("Configured extractor does not support repair")
        return await method(*args, **kwargs)

    async def answer(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._getter().answer(*args, **kwargs)


BackendFactory = Callable[[], AbstractAsyncContextManager[SupplyChainBackend]]


@asynccontextmanager
async def default_backend_factory(
    config: PrecisoMCPConfig | None = None,
) -> AsyncIterator[SupplyChainBackend]:
    """Open the configured MCP client without accepting credentials from HTTP."""

    async with PrecisoMCPClient(config) as client:
        yield client


def create_app(
    backend_factory: BackendFactory | None = None,
    *,
    config: PrecisoMCPConfig | None = None,
    extractor: Extractor | None = None,
    registry: dict[str, Any] | None = None,
    artifact_dir: Path | None = None,
    upload_dir: Path | None = None,
) -> FastAPI:
    """Create the local API with an injectable MCP backend factory.

    Tests and embedding applications can provide an in-memory/fake backend.
    The default factory reads MCP configuration from server-side environment
    variables via :class:`PrecisoMCPConfig`; request bodies never contain API
    keys or provider settings.
    """

    load_local_env()
    factory = backend_factory or (lambda: default_backend_factory(config))
    extraction_service = extractor or ClaudeExtractor.from_environment()
    canonical_registry = registry or load_registry()
    extraction_artifact_dir = artifact_dir or DEFAULT_EXTRACTION_ARTIFACT_DIR
    source_store = SourceStore(upload_dir or DEFAULT_UPLOAD_DIR)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with factory() as backend:
            app.state.application = SupplyChainApplication(backend)
            app.state.extraction_service = extraction_service
            extraction_artifact_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = extraction_artifact_dir.parent / "supply_center_runs.sqlite"
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                await checkpointer.setup()
                app.state.agent_runtime = SupplyAgentRuntime(
                    AgentDependencies(
                        application=app.state.application,
                        extractor=ExtractorProxy(lambda: app.state.extraction_service),
                        registry=canonical_registry,
                        artifacts=ExtractionArtifactStore(extraction_artifact_dir),
                    ),
                    checkpointer,
                )
                yield

    app = FastAPI(
        title="SUPPLY CENTER API",
        version="0.1.0",
        lifespan=lifespan,
    )

    def application() -> SupplyChainApplication:
        return app.state.application

    def current_extractor() -> Extractor:
        return app.state.extraction_service

    def agent_runtime() -> SupplyAgentRuntime:
        return app.state.agent_runtime

    def source_records(documents: list[SourceDocument]) -> list[dict[str, Any]]:
        records = []
        for document in documents:
            source_id = hashlib.sha256(
                f"{document.name}\0{document.content}".encode()
            ).hexdigest()[:24]
            records.append(
                {
                    "source_id": source_id,
                    "name": document.name,
                    "content": document.content,
                    "extension": Path(document.name).suffix.lower(),
                    "status": "uploaded",
                }
            )
        return records

    @app.post("/api/sources")
    async def upload_sources(documents: list[SourceDocument]) -> dict[str, Any]:
        try:
            return {"sources": [source_store.create(name=item.name, content=item.content) for item in documents]}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def public_state(snapshot: RunSnapshot) -> dict[str, Any]:
        state = dict(snapshot.state)
        state["uploaded_sources"] = [
            {key: value for key, value in source.items() if key != "content"}
            for source in state.get("uploaded_sources", [])
        ]
        state["extraction_results"] = {
            source_id: {
                **result,
                "artifact_url": (
                    f"/api/extractions/{Path(result['artifact_name']).name}"
                    if result.get("artifact_name")
                    else None
                ),
            }
            for source_id, result in state.get("extraction_results", {}).items()
        }
        return state

    def run_response(snapshot: RunSnapshot) -> dict[str, Any]:
        return {
            "status": snapshot.status,
            "thread_id": snapshot.thread_id,
            "conversation_id": snapshot.state.get("conversation_id", snapshot.thread_id),
            "run_id": snapshot.state.get("run_id"),
            "intent": snapshot.state.get("intent"),
            "awaiting_approval": snapshot.status == "awaiting_approval",
            "interrupts": snapshot.interrupts,
            "state": public_state(snapshot),
            "events": snapshot.state.get("events", []),
            "answer": snapshot.state.get("final_answer"),
        }

    def started_run_response(*, thread_id: str, run_id: str) -> dict[str, Any]:
        return {
            "status": "running",
            "thread_id": thread_id,
            "conversation_id": thread_id,
            "run_id": run_id,
            "awaiting_approval": False,
            "events_url": f"/api/events/{run_id}",
        }

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        engine = await application().status()
        return {"engine": engine, "extractor": current_extractor().status()}

    @app.post("/api/provider")
    async def configure_provider(request: ProviderConfigurationRequest) -> dict[str, Any]:
        app.state.extraction_service = ClaudeExtractor(
            api_key=request.api_key,
            model=request.model,
        )
        return {
            "status": "success",
            "extractor": current_extractor().status(),
            "notice": "Provider configured in memory for this local API process.",
        }

    @app.get("/api/capabilities")
    async def capabilities() -> dict[str, Any]:
        facilities = [
            {
                "canonical_id": item["canonical_id"],
                "display_name": item.get("display_name", item["canonical_id"]),
            }
            for item in canonical_registry.get("entities", [])
            if item.get("entity_type") == "FACILITY"
        ]
        return {
            "workspace": "supply_chain",
            "extractor": current_extractor().status(),
            "facilities": facilities,
            "supported_intents": ["facility_unavailable"],
            "unsupported": ["forecasting", "inventory", "severity", "delay_prediction"],
        }

    @app.post("/api/extract")
    async def extract(request: ExtractionRequest) -> dict[str, Any]:
        extractor_service = current_extractor()
        if not extractor_service.configured:
            raise HTTPException(status_code=503, detail=extractor_service.status())
        try:
            result = await extractor_service.extract(
                [document.model_dump() for document in request.documents],
                snapshot_effective_date=request.snapshot_effective_date.isoformat(),
                registry=canonical_registry,
            )
            extraction_artifact_dir.mkdir(parents=True, exist_ok=True)
            payloads = result.get("payloads") if isinstance(result, dict) else None
            if isinstance(payloads, list) and len(payloads) == len(request.documents):
                store = ExtractionArtifactStore(extraction_artifact_dir)
                artifacts = []
                for document, payload in zip(request.documents, payloads, strict=True):
                    source_id = source_records([document])[0]["source_id"]
                    artifact = store.write(document.name, source_id, payload)
                    artifacts.append(
                        {
                            "name": artifact["artifact_name"],
                            "url": f"/api/extractions/{artifact['artifact_name']}",
                            "description": "Independent Claude extraction awaiting PRECISO validation.",
                        }
                    )
                return {**result, "artifacts": artifacts}
            artifact_path = extraction_artifact_dir / EXTRACTION_ARTIFACT_NAME
            temporary_path = artifact_path.with_suffix(".tmp")
            temporary_path.write_text(json.dumps(result["payload"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary_path.replace(artifact_path)
            return {
                **result,
                "artifact": {
                    "name": EXTRACTION_ARTIFACT_NAME,
                    "url": "/api/extractions/preciso_extract.json",
                    "description": "Exact Claude extraction payload awaiting or accepted by PRECISO.",
                },
            }
        except ExtractionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/extractions/preciso_extract.json")
    async def get_extraction_artifact() -> FileResponse:
        artifact_path = extraction_artifact_dir / EXTRACTION_ARTIFACT_NAME
        if not artifact_path.is_file():
            raise HTTPException(status_code=404, detail="No extraction artifact has been created yet.")
        return FileResponse(
            artifact_path,
            media_type="application/json",
            filename=EXTRACTION_ARTIFACT_NAME,
        )

    @app.get("/api/extractions/{artifact_name}")
    async def get_named_extraction_artifact(artifact_name: str) -> FileResponse:
        safe_name = Path(artifact_name).name
        if safe_name != artifact_name or not safe_name.endswith("_extracted.json"):
            raise HTTPException(status_code=400, detail="Invalid extraction artifact name")
        artifact_path = extraction_artifact_dir / safe_name
        if not artifact_path.is_file():
            raise HTTPException(status_code=404, detail="Extraction artifact not found")
        return FileResponse(artifact_path, media_type="application/json", filename=safe_name)

    @app.post("/api/investigate")
    async def investigate(request: FacilityInvestigationRequest) -> dict[str, Any]:
        return await application().investigate_facility(
            request.facility_id,
            max_paths=request.max_paths,
        )

    @app.get("/api/investigate")
    async def investigate_get(
        facility_id: str = Query(min_length=1),
        max_paths: int = Query(default=100, ge=1, le=MAX_PATHS),
    ) -> dict[str, Any]:
        return await application().investigate_facility(facility_id, max_paths=max_paths)

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, Any]:
        intent = resolve_chat_intent(request.message, canonical_registry)
        if intent.get("status") != "resolved":
            return {**intent, "workspace": "supply_chain"}
        result = await application().investigate_facility(
            str(intent["facility_id"]), max_paths=request.max_paths
        )
        return {
            "status": result.get("status", "error"),
            "intent": intent["intent"],
            "facility_name": intent["facility_name"],
            "result": result,
        }

    @app.post("/api/grounded-answer")
    async def grounded_answer(request: GroundedAnswerRequest) -> dict[str, Any]:
        try:
            return await current_extractor().answer(request.question, request.investigation)
        except ExtractionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/runs")
    async def start_agent_run(request: AgentRunRequest) -> dict[str, Any]:
        thread_id = request.conversation_id or f"conversation:{uuid.uuid4().hex}"
        initial: dict[str, Any] = {
            "conversation_id": thread_id,
            "run_id": uuid.uuid4().hex,
            "user_query": request.message,
            "snapshot_effective_date": request.snapshot_effective_date.isoformat(),
            "messages": [{"role": "user", "content": request.message}],
        }
        if request.source_ids is not None and request.documents is not None:
            raise HTTPException(status_code=422, detail="Submit documents or source_ids, not both")
        if request.source_ids is not None:
            try:
                initial["uploaded_sources"] = [source_store.get(source_id) for source_id in request.source_ids]
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=404, detail=f"Unknown source: {exc}") from exc
        elif request.documents is not None:
            initial["uploaded_sources"] = source_records(request.documents)
        run_id = await agent_runtime().start(thread_id, initial)
        return started_run_response(thread_id=thread_id, run_id=run_id)

    @app.get("/api/runs/{thread_id}")
    async def get_agent_run(thread_id: str) -> dict[str, Any]:
        try:
            return run_response(await agent_runtime().snapshot(thread_id))
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Run not found: {exc}") from exc

    @app.post("/api/runs/{thread_id}/approval")
    async def approve_agent_run(thread_id: str, request: ApprovalRequest) -> dict[str, Any]:
        try:
            run_id = await agent_runtime().resume_live(thread_id, approved=request.approved)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"Run could not be resumed: {exc}") from exc
        return started_run_response(thread_id=thread_id, run_id=run_id)

    @app.get("/api/events/{run_id}")
    async def agent_events(run_id: str) -> StreamingResponse:
        try:
            agent_runtime().run_for_id(run_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Run not found: {exc}") from exc

        async def stream() -> AsyncIterator[str]:
            async for event in agent_runtime().events(run_id):
                yield f"event: {event.get('type', 'execution')}\ndata: {json.dumps(event)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run("preciso_supply_agent.api:create_app", factory=True, host="127.0.0.1", port=8765)


if __name__ == "__main__":  # pragma: no cover
    main()
