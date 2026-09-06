# SUPPLY CENTER

Local-first, evidence-backed supply-chain investigation for analysts.

Backed by PRECISO, the authoritative GraphRAG/MCP engine pinned at
[`bfb009ba70d888d7360b2cb4f0adb8bb55368e21`](https://github.com/Preciso-GR/preciso-graphrag/commit/bfb009ba70d888d7360b2cb4f0adb8bb55368e21).

SUPPLY CENTER is the application and analyst experience. This repository intentionally contains
no duplicate graph store, extraction engine, or dependency traversal. Those responsibilities
remain in the pinned PRECISO engine.

## Current application

The responsive web experience is now framed as a supply-chain analyst console:

- a working home screen with a `Get Started` entry into the analyst chat;
- a setup panel for PRECISO MCP status, source documents, and local LLM provider setup;
- a conversation-first analyst workspace for supported dependency-tracing questions;
- local text-document upload for Markdown, text, CSV, and JSON sources;
- runtime Anthropic/Claude extraction configuration kept only in the local API process;
- relationship review controls before ingestion;
- evidence and source-chunk inspection;
- explicit MCP, provider, extraction, ingestion, and evidence states.

The local HTTP API delegates these operations to PRECISO:

- `get_server_status(workspace="supply_chain")`
- `ingest_graph_tool(..., workspace="supply_chain")`
- `query_facility_unavailable(..., workspace="supply_chain")`

The backend returns ordered facility → component → product paths, source excerpts for
every edge, snapshot metadata, and truncation/completeness. It does not predict delay,
inventory shortage, production stoppage, severity, or financial impact.

The browser keeps the local conversation and the latest untouched model output in local storage.
Relationships are never ingested until they are explicitly accepted in the review list and pass
PRECISO's strict supply-chain validation. Authentication and multi-user durable sessions are
intentionally outside this prototype. The UI no longer preloads a synthetic Northbridge fixture;
analysts start from their own documents and the configured PRECISO MCP workspace.

## Development setup

Install Preciso GraphRAG at the pinned commit in a separate checkout, then install this
application package:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export PRECISO_MCP_CWD=/absolute/path/to/preciso-graphrag
export PRECISO_MCP_COMMAND=python3
export PRECISO_MCP_ARGS='-m preciso_mcp.server'
export GRAPHRAG_MCP_WORKDIR=/absolute/path/to/preciso-supply-chain/data/preciso
export GRAPHRAG_EMBEDDING_PROVIDER=fallback
export SUPPLY_CENTER_CLAUDE_MODEL=claude-sonnet-5
supply-center-api
```

The local API reads `.env` on startup for development, without overriding variables already
exported in the shell. You can also enter an Anthropic key in the Supply Center setup panel; it is
held in memory by the local API process and is not returned to the browser or written to disk.
Never place the key in `web/`; Vite client variables are visible to the browser.

The client starts the configured Preciso MCP stdio server; it does not reimplement
backend behavior. In a second terminal, start the web application:

```bash
cd web
npm install
npm run dev
```

Vite proxies `/api` to the local SUPPLY CENTER API on `127.0.0.1:8765`. The fallback embedding
is suitable for reproducible local development, not an Ollama embedding evaluation. Without an
Anthropic key, fresh model extraction is disabled; ingestion and deterministic investigation
still depend on reviewed graph payloads accepted by PRECISO.

Product reverse tracing, shared-dependency analysis, data-gap claims, forecasting,
inventory, and live monitoring are not implemented here.

## Verification

```bash
python3 -m pytest
python3 -m ruff check src tests
cd web && npm run build
```
