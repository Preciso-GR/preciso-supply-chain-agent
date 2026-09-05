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
- a ChatGPT Work-style local analyst workspace;
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

Raw-document upload, LLM extraction orchestration, provider selection, authentication, and
durable application sessions are not implemented. The current workspace uses the labelled
synthetic fixture unless the local PRECISO backend contains the Northbridge dataset.

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
supply-center-api
```

The client starts the configured Preciso MCP stdio server; it does not reimplement
backend behavior. In a second terminal, start the web application:

```bash
cd web
npm install
npm run dev
```

Vite proxies `/api` to the local SUPPLY CENTER API on `127.0.0.1:8765`. The fallback embedding
is suitable for reproducible synthetic data, not an Ollama embedding evaluation.

Product reverse tracing, shared-dependency analysis, data-gap claims, forecasting,
inventory, and live monitoring are not implemented here.

## Verification

```bash
python3 -m pytest
python3 -m ruff check src tests
cd web && npm run build
```
