"""FastAPI adapter for the SATURN supply-chain frontend.

This module is intentionally a thin HTTP boundary.  The configured Preciso
MCP server remains responsible for validation, persistence, and dependency
traversal; this API only enforces the frontend request envelope and forwards
the existing application contract.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, AsyncIterator, Callable, Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from preciso_supply_agent.application import SupplyChainApplication, SupplyChainBackend
from preciso_supply_agent.client import PrecisoMCPClient, PrecisoMCPConfig


MAX_PATHS = 1000


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
) -> FastAPI:
    """Create the local API with an injectable MCP backend factory.

    Tests and embedding applications can provide an in-memory/fake backend.
    The default factory reads MCP configuration from server-side environment
    variables via :class:`PrecisoMCPConfig`; request bodies never contain API
    keys or provider settings.
    """

    factory = backend_factory or (lambda: default_backend_factory(config))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with factory() as backend:
            app.state.application = SupplyChainApplication(backend)
            yield

    app = FastAPI(
        title="SATURN Supply Center API",
        version="0.1.0",
        lifespan=lifespan,
    )

    def application() -> SupplyChainApplication:
        return app.state.application

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return await application().status()

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

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run("preciso_supply_agent.api:create_app", factory=True, host="127.0.0.1", port=8765)


if __name__ == "__main__":  # pragma: no cover
    main()
