# PRECISO Supply Center Architecture

Status: current implementation snapshot, September 2026.

## What This Is

PRECISO Supply Center is a local-first, chat-based supply-chain investigation application. An analyst supplies source documents and asks a dependency question. The application turns each document into a proposed structured extraction, validates it with PRECISO, requires a human decision before it changes the graph, then answers from the persisted graph.

It is not a general web-search assistant and it is not a second GraphRAG engine. The bundled PRECISO engine is the authority for extraction validation, graph persistence, embeddings, retrieval, evidence, and dependency traversal.

The governing rule is:

> Claude proposes. LangGraph orchestrates. Supply Center manages sources and artifacts. PRECISO validates and stores. Human approval controls graph mutation.

## Who Uses It

The intended V1 user is a supply-chain analyst or researcher investigating relationships such as component suppliers, factories, products, and announced supply arrangements. The current application is suitable for local demonstrations, controlled research, and single-operator investigations.

It is not yet a multi-user production system: it has no authentication, roles, tenancy, shared-workspace controls, or hosted deployment model.

## System Shape

```text
Browser UI (Vite)
    |  source upload, chat, approval, live progress, Markdown answers
    |  HTTP + Server-Sent Events
    v
FastAPI application
    |  source store, artifact store, API boundary
    v
LangGraph workflow with SQLite checkpoints
    |  Claude extraction / repair / grounded synthesis
    |  MCP stdio client
    v
Bundled PRECISO GraphRAG MCP engine
    |  validation, ingestion, graph/vector/evidence persistence, retrieval
    v
data/preciso/supply_chain
```

### Main Components

| Area | Location | Responsibility |
| --- | --- | --- |
| Browser | `web/src/main.js` | Uploads source text, starts and resumes runs, displays SSE progress, approval, graph-answer state, and sanitized Markdown. |
| API | `src/preciso_supply_agent/api.py` | Local FastAPI boundary for sources, agent runs, snapshots, artifacts, and SSE. |
| Workflow | `src/preciso_supply_agent/agent/graph.py` | Explicit LangGraph nodes and routing for status, extraction, validation, repair, approval, ingestion, query, and synthesis. |
| Runtime | `src/preciso_supply_agent/agent/runtime.py` | Runs checkpointed LangGraph threads and publishes node events through SSE. |
| Source storage | `src/preciso_supply_agent/documents/` | Stores supported uploaded text sources and resolves source IDs for follow-up turns. |
| Artifacts | `src/preciso_supply_agent/agent/artifacts.py` | Creates one extraction JSON artifact per source and applies bounded structured repair patches. |
| MCP client | `src/preciso_supply_agent/client.py` | Starts and verifies the bundled PRECISO MCP server over stdio. |
| Engine | `engine/preciso-graphrag` | Vendored PRECISO GraphRAG engine, pinned at `710ba66d929fa85b449e6ba256dcbd04f7e891c9`. |

## Implemented Workflow

```text
Upload .md/.txt/.csv/.json files
    -> persist each source and obtain a source ID
    -> start LangGraph run
    -> check PRECISO server status
    -> classify request intent
    -> read each new source once
    -> Claude creates one extraction artifact per source
    -> PRECISO validate_extraction
    -> bounded minimal repair and revalidation when required
    -> LangGraph approval interrupt
    -> human Approve or Reject
    -> on approval: PRECISO ingest_from_file
    -> query_graph_tool for graph questions
    -> Claude synthesizes only from returned PRECISO context
    -> browser renders the answer as sanitized Markdown
```

### Request Intents

The workflow has three deterministic intent classes:

- `new_sources`: process supplied documents without a graph question.
- `new_sources_and_query`: process documents, pause for approval, ingest only when approved, then answer the question.
- `graph_query`: query existing persisted graph knowledge without re-extracting documents.

Follow-up turns reference persisted source IDs rather than retransmitting raw source content. The graph tests cover this behavior.

### Guardrails That Exist Today

- A document produces one independent extraction artifact.
- Extraction artifacts are validated by PRECISO before they can be approved.
- Validation repair is bounded and uses structured, targeted edits instead of blind text replacement.
- Approval is a LangGraph interrupt before `ingest_from_file`.
- Reject resumes the same thread but does not call ingestion.
- Normal workflow mutation has one route: `ingest_from_file` after approval.
- API startup verifies real MCP discovery for `get_server_status`, `validate_extraction`, `ingest_from_file`, and `query_graph_tool`.
- Claude answer synthesis receives PRECISO query context, not the original raw documents by default.
- Browser Markdown is parsed with `marked` and sanitized with DOMPurify before insertion into the page.

## Data and Persistence

| Path | Content | Git status |
| --- | --- | --- |
| `engine/preciso-graphrag/` | Vendored engine source only. | Committed |
| `engine/PRECISO_VERSION` | Exact upstream engine revision. | Committed |
| `data/preciso/supply_chain/` | PRECISO graph, vector, evidence, and manifest runtime data. | Ignored |
| `uploads/` | Application-owned raw uploaded files and `sources.json` index. | Ignored |
| `.runtime/extractions/` | Extraction artifacts and LangGraph SQLite checkpoints. | Ignored |

The default MCP configuration resolves the engine relative to the application root and sets `GRAPHRAG_MCP_WORKDIR` to `<app-root>/data/preciso`. A separate PRECISO checkout and a developer-specific engine path are not required.

## Runtime Contracts

### MCP Tools Required at Startup

```text
get_server_status
validate_extraction
ingest_from_file
query_graph_tool
```

### Browser/API Contract

- `POST /api/sources`: persists supported source text and returns source records.
- `POST /api/runs`: starts an asynchronous LangGraph run.
- `GET /api/events/{run_id}`: streams real LangGraph node events as SSE.
- `GET /api/runs/{thread_id}`: returns the checkpointed run snapshot.
- `POST /api/runs/{thread_id}/approval`: resumes the approval interrupt.
- `GET /api/extractions/{artifact_name}`: downloads an extraction artifact.

Legacy or lower-level endpoints also remain for extraction, intent experiments, provider configuration, and direct investigation. New UI work should prefer the stateful `/api/runs` workflow rather than building on those endpoints.

## What Is Built and Verified

The repository contains unit and integration coverage for MCP configuration, source persistence, artifact editing, graph lifecycle, approval/rejection behavior, API run streaming, intent routing, and bundled MCP tool discovery.

The completed Panasonic browser acceptance flow demonstrated these product behaviors with the real bundled engine:

- independent extraction and validation for the uploaded Panasonic, Harbinger, Zoox, and Lucid source documents;
- explicit approval before graph ingestion;
- an answer identifying the documented products that use Panasonic 2170 cells; and
- a follow-up answer preserving the important qualification that Zoox's initial supply is from Japan and Kansas expansion is planned for the future, not current supply.

The frontend production build is provided by Vite. The Python package is configured with setuptools and includes its prompts and resource data as package data.

## Known Limitations

These are current limitations, not claims about completed functionality.

1. **Answer transport is not token-by-token yet.** The backend emits one complete `answer.token` event with `streamed: false`. The browser can update as tokens arrive, but the server must stream provider tokens to create the ChatGPT-style gradual reveal.
2. **Evidence presentation needs normalization.** The Panasonic answer was graph-grounded, but the UI reported no directly citable evidence items. The application currently looks only in selected `raw_data` fields; it should normalize the exact bundled-engine response schema and render evidence excerpts and source links beside the answer.
3. **The Graph tab is a placeholder.** It describes persisted graph state but does not visualize nodes, relationships, paths, or query evidence.
4. **Source browsing is session-oriented.** Sources persist locally, but the browser does not yet have a full source-library API for listing, reopening, deleting, or reusing uploads across a fresh browser session.
5. **Source index portability can improve.** `uploads/sources.json` currently records absolute storage paths. The engine itself is package-safe, but storing paths relative to the upload root would make moving an existing runtime directory more robust.
6. **Input support is text-only.** Markdown, text, CSV, and JSON are supported. PDF, Office documents, OCR, URLs, and connectors are not implemented.
7. **Operational hardening is absent.** There is no authentication, authorization, TLS termination, rate limiting, audit UI, background job recovery across process failure, or multi-user isolation.
8. **No browser test suite exists.** Python tests cover the backend contract; the Vite app has a build check but no Playwright/Cypress component or end-to-end suite.
9. **Graph quality remains source- and model-dependent.** Validation prevents structurally invalid extraction artifacts; it cannot establish that an otherwise valid model extraction is factually complete or correct without review and source provenance.

## Recommended Next Changes

### Priority 1: Trust and Answer Quality

1. Normalize `query_graph_tool` output into a stable internal evidence model.
2. Render cited source excerpts, reference URLs, and relationship provenance next to each answer.
3. Add tests that assert temporal qualifiers survive from evidence through grounded answer generation.
4. Make approval reviewable: show extraction JSON diff/detail before the Approve action, not only entity and relationship counts.

### Priority 2: Product Workflow

1. Implement a real Graph view with query paths, nodes, edges, and source evidence.
2. Add source-library endpoints and UI for list, preview, remove, and reuse.
3. Persist relative source-storage paths and add a runtime migration for existing source indexes.
4. Stream Claude provider tokens from the backend and keep Markdown rendering stable while partial syntax is incomplete.

### Priority 3: Reliability and Operations

1. Add a restart/recovery test using the actual SQLite checkpoint and persisted engine data.
2. Add idempotency and duplicate-ingestion behavior tests against the real engine.
3. Add structured logs, health diagnostics, and an operator-facing status view for Ollama, MCP, graph storage, and Claude configuration.
4. Define authentication, tenancy, retention, and backup requirements before exposing the application beyond a trusted local environment.

### Priority 4: Broader Input and Evaluation

1. Add PDF and Office parsing with extraction-quality tests before advertising the formats.
2. Create a versioned acceptance corpus with expected graph relationships, citations, and temporal claims.
3. Measure extraction precision/recall, validation/repair rates, answer grounding quality, and latency against that corpus.

## Development Checks

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
cd web && npm run build
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation -w /tmp/wheels
RUN_BUNDLED_MCP_INTEGRATION=1 .venv/bin/python -m pytest tests/test_bundled_mcp_integration.py
```

The real bundled MCP integration and full browser acceptance flow require the engine dependencies, a healthy local Ollama embedding model, and an Anthropic API key for Claude extraction and synthesis.
