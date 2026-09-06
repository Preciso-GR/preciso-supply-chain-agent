# SUPPLY CENTER

Local-first, evidence-backed supply-chain investigation for analysts.

**Powered by PRECISO**, the authoritative GraphRAG/MCP engine pinned at
[`bfb009ba70d888d7360b2cb4f0adb8bb55368e21`](https://github.com/Preciso-GR/preciso-graphrag/commit/bfb009ba70d888d7360b2cb4f0adb8bb55368e21).

SUPPLY CENTER is the application and analyst experience. This repository intentionally contains
no duplicate graph store, extraction engine, or dependency traversal. Those responsibilities
remain in the pinned PRECISO engine.

## Current application

The responsive web experience includes:

- a product homepage using the SUPPLY CENTER dependency-path identity;
- a Codex-style, conversation-first local analyst workspace;
- local text-document upload for Markdown, text, CSV, and JSON sources;
- optional Claude extraction, configured only in the local API process;
- table-based relationship review controls;
- the verified Northbridge dependency-path demonstration;
- evidence and source-chunk inspection;
- explicit `Fixture preview`, `PRECISO connected`, and live-data states.

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
intentionally outside this prototype. The labelled synthetic fixture remains available when no
Claude key is configured.

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
export ANTHROPIC_API_KEY=your_local_key
export SUPPLY_CENTER_CLAUDE_MODEL=claude-sonnet-5
supply-center-api
```

You can copy `.env.example` to `.env`, but the application does not load `.env` implicitly.
Export it into the API process (for example, `set -a; source .env; set +a`) or use your process
manager's environment support. Never place the key in `web/`; Vite client variables are visible
to the browser.

The client starts the configured Preciso MCP stdio server; it does not reimplement
backend behavior. In a second terminal, start the web application:

```bash
cd web
npm install
npm run dev
```

Vite proxies `/api` to the local SUPPLY CENTER API on `127.0.0.1:8765`. The fallback embedding
is suitable for reproducible synthetic data, not an Ollama embedding evaluation. Without an
Anthropic key, the curated review, ingestion, deterministic query, and evidence workflows still
run; only fresh model extraction is disabled.

Product reverse tracing, shared-dependency analysis, data-gap claims, forecasting,
inventory, and live monitoring are not implemented here.

## Verification

```bash
python3 -m pytest
python3 -m ruff check src tests
cd web && npm run build
```
