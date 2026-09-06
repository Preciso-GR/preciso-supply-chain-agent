"""FastAPI adapter for the SUPPLY CENTER frontend.

This module is intentionally a thin HTTP boundary.  The configured Preciso
MCP server remains responsible for validation, persistence, and dependency
traversal; this API only enforces the frontend request envelope and forwards
the existing application contract.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
import json
from pathlib import Path
from typing import Any, AsyncContextManager, AsyncIterator, Callable, Literal, Protocol

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from preciso_supply_agent.application import SupplyChainApplication, SupplyChainBackend
from preciso_supply_agent.client import PrecisoMCPClient, PrecisoMCPConfig
from preciso_supply_agent.extraction import ClaudeExtractor, ExtractionError, load_registry
from preciso_supply_agent.intent import resolve_chat_intent


MAX_PATHS = 1000
MAX_DOCUMENTS = 8
MAX_DOCUMENT_CHARACTERS = 250_000
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_EXTRACTION_PATH = (
    REPOSITORY_ROOT / "fixtures" / "supply_chain" / "expected_extraction.json"
)


class ApprovedIngestionRequest(BaseModel):
    """The only ingestion shape accepted by the UI boundary."""

    model_config = ConfigDict(extra="forbid")

    approved: Literal[True]
    payload: dict[str, Any]


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


class ChatRequest(BaseModel):
    """Natural-language entrypoint for the supported deterministic scenario."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    max_paths: int = Field(default=100, ge=1, le=MAX_PATHS)


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


BackendFactory = Callable[[], AsyncContextManager[SupplyChainBackend]]


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
) -> FastAPI:
    """Create the local API with an injectable MCP backend factory.

    Tests and embedding applications can provide an in-memory/fake backend.
    The default factory reads MCP configuration from server-side environment
    variables via :class:`PrecisoMCPConfig`; request bodies never contain API
    keys or provider settings.
    """

    factory = backend_factory or (lambda: default_backend_factory(config))
    extraction_service = extractor or ClaudeExtractor.from_environment()
    canonical_registry = registry or load_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with factory() as backend:
            app.state.application = SupplyChainApplication(backend)
            yield

    app = FastAPI(
        title="SUPPLY CENTER API",
        version="0.1.0",
        lifespan=lifespan,
    )

    def application() -> SupplyChainApplication:
        return app.state.application

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        engine = await application().status()
        return {"engine": engine, "extractor": extraction_service.status()}

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
            "extractor": extraction_service.status(),
            "facilities": facilities,
            "supported_intents": ["facility_unavailable"],
            "unsupported": ["forecasting", "inventory", "severity", "delay_prediction"],
        }

    @app.get("/api/sample")
    async def sample() -> dict[str, Any]:
        return {
            "status": "success",
            "mode": "curated_sample",
            "notice": "Manually authored fixture; not evidence of extraction accuracy.",
            "payload": json.loads(SAMPLE_EXTRACTION_PATH.read_text(encoding="utf-8")),
        }

    @app.post("/api/extract")
    async def extract(request: ExtractionRequest) -> dict[str, Any]:
        if not extraction_service.configured:
            raise HTTPException(status_code=503, detail=extraction_service.status())
        try:
            return await extraction_service.extract(
                [document.model_dump() for document in request.documents],
                snapshot_effective_date=request.snapshot_effective_date.isoformat(),
                registry=canonical_registry,
            )
        except ExtractionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/ingest")
    async def ingest(request: ApprovedIngestionRequest) -> dict[str, Any]:
        return await application().ingest_reviewed_extraction(request.payload)

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

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run("preciso_supply_agent.api:create_app", factory=True, host="127.0.0.1", port=8765)


if __name__ == "__main__":  # pragma: no cover
    main()
