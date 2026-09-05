# Preciso Supply Chain

Hackathon application layer for evidence-backed supply-chain investigation.

**Powered by PRECISO**, the authoritative GraphRAG/MCP engine pinned at
[`bfb009ba70d888d7360b2cb4f0adb8bb55368e21`](https://github.com/Preciso-GR/preciso-graphrag/commit/bfb009ba70d888d7360b2cb4f0adb8bb55368e21).

This repository intentionally contains no graph store, SQLite schema, extraction engine,
or dependency traversal. It calls Preciso's existing supply-chain MCP tools and will later
provide the analyst UI around those supported results.

## Current scope

- `get_server_status(workspace="supply_chain")`
- `ingest_graph_tool(..., workspace="supply_chain")`
- `query_facility_unavailable(..., workspace="supply_chain")`

The backend returns ordered facility → component → product paths, source excerpts for
every edge, snapshot metadata, and truncation/completeness. It does not predict delay,
inventory shortage, production stoppage, severity, or financial impact.

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
```

The client starts the configured Preciso MCP stdio server; it does not reimplement
backend behavior. The fallback embedding is suitable for reproducible synthetic data,
not an Ollama embedding evaluation.

## Product direction

The next work is UI planning and implementation: facility selection, cited path view, and
evidence inspection. Product reverse tracing, shared-dependency analysis, data-gap claims,
forecasting, inventory, and live monitoring are not implemented here.

## Verification

```bash
python3 -m pytest
python3 -m ruff check src tests
```

# preciso-supply-chain-agent
