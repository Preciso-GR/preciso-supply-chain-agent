# PRECISO Supply-Chain Agent

A focused, standalone MCP server for deterministic supply-chain dependency analysis.
It answers which products have documented dependencies on an unavailable facility,
through which components, and which source excerpts support every edge.

The runtime does not import or read the sibling `preciso-graphrag` or `preciso-agent`
repositories. The first release intentionally has no vector search, generic RAG, finance
providers, Neo4j, Qdrant, UI, or LLM extraction.

## Domain contract

Only these directed facts are accepted:

```text
COMPANY -> OPERATES -> FACILITY
FACILITY -> MANUFACTURES -> COMPONENT
COMPONENT -> USED_IN -> PRODUCT
```

Every entity and relationship must cite a chunk included in its reviewed extraction
payload. Validation occurs before writes, and the whole document commits in one SQLite
transaction. Queries fail closed if ingestion or path evidence is incomplete.

## Install and run

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/preciso-supply-mcp
```

The server uses stdio transport by default and stores data at
`data/supply_chain.sqlite3`. Set `PRECISO_SUPPLY_DB` to choose another SQLite path.

The MCP surface contains exactly three tools:

- `get_supply_chain_status`
- `ingest_supply_chain`
- `investigate_facility`

`ingest_supply_chain` accepts the reviewed payload shape demonstrated by
`fixtures/supply_chain/expected_extraction.json`. `investigate_facility` accepts a
canonical facility ID and an optional positive `max_paths` limit.

## Reproduce the curated demo

From the repository root:

```bash
PYTHONPATH=src python3 scripts/demo.py
```

The demo uses the reviewed synthetic fixture. It is a deterministic engine test, not an
LLM extraction claim. It prints the Northbridge result, unresolved Plant 7 result, and a
missing-evidence fail-closed result against isolated temporary databases.

## Product limitation

Results mean **potential exposure through documented dependencies in the loaded
snapshot**. They do not establish production stoppage, severity, financial impact,
inventory shortage, lead-time impact, capacity, or a business-continuity outcome.

See [docs/SUPPLY_CHAIN_CORE_EXTRACTION.md](docs/SUPPLY_CHAIN_CORE_EXTRACTION.md) for the
dependency audit, architecture decision, verification evidence, and known limitations.

# preciso-supply-chain-agent
