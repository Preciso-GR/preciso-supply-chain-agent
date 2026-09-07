# SUPPLY CENTER

Local-first, evidence-backed supply-chain investigation. This is one repository:
the bundled PRECISO GraphRAG engine lives in `engine/preciso-graphrag` at
`710ba66d929fa85b449e6ba256dcbd04f7e891c9`.

## Architecture

Claude proposes extractions and minimal repairs. LangGraph owns lifecycle and
approval interrupts. Supply Center owns uploaded sources, extraction artifacts,
conversations, and live SSE events. PRECISO validates, embeds, merges, stores,
retrieves, and returns graph evidence. Human approval is required before graph
persistence.

```text
source -> extraction artifact -> PRECISO validation -> repair if needed
-> human approval -> PRECISO ingest_from_file -> query_graph_tool -> evidence
-> Claude grounded answer
```

There is no browser or legacy HTTP path that mutates PRECISO outside this
workflow. One source produces one extraction artifact. Follow-up turns send
source IDs, never raw document content again.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/supply-center-api
```

In another terminal:

```bash
cd web
npm install
npm run dev
```

The API automatically launches `engine/preciso-graphrag/scripts/mcp_launcher.sh`.
No separate PRECISO checkout or `PRECISO_MCP_CWD` is needed. Set
`ANTHROPIC_API_KEY` for fresh Claude extraction and grounded answers.

PRECISO uses Ollama embeddings by default (`mxbai-embed-large`). Run Ollama and
pull that model for semantic GraphRAG. Without Ollama, status is degraded and
fallback dimensional behavior is useful only for plumbing, not retrieval-quality
evaluation.

## Runtime files

- `engine/preciso-graphrag`: vendored engine source; do not store user data here.
- `data/preciso/supply_chain`: graph, vectors, evidence, and manifests.
- `uploads`: application-owned raw source records.
- `.runtime/extractions`: Supply Center extraction artifacts and checkpoints.

Graph data persists across application restarts. Runtime directories are ignored
by Git.

## Supported sources

Markdown (`.md`), text (`.txt`), CSV (`.csv`), and JSON (`.json`) are supported.
PDF is not currently supported.

## MCP contract

Startup requires and verifies:

- `get_server_status`
- `validate_extraction`
- `ingest_from_file`
- `query_graph_tool`

The browser starts a run then connects to `/api/events/{run_id}`. Events come
from actual LangGraph node execution and the stream closes at completion or the
approval pause; resuming approval starts a new live stream for the same run.

## Verification

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
cd web && npm run build
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation -w /tmp/wheels
RUN_BUNDLED_MCP_INTEGRATION=1 .venv/bin/python -m pytest tests/test_bundled_mcp_integration.py
```

The bundled integration test validates real MCP discovery and the runtime data
location. A full three-document Panasonic acceptance test additionally requires
an Anthropic key and a healthy local Ollama embedding model.
