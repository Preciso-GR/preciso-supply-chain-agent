from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from preciso_supply_agent.agent.artifacts import ExtractionArtifactStore
from preciso_supply_agent.agent.graph import AgentDependencies
from preciso_supply_agent.agent.runtime import SupplyAgentRuntime
from preciso_supply_agent.application import SupplyChainApplication


class GraphBackend:
    def __init__(
        self,
        *,
        permanently_invalid: set[str] | None = None,
        invalid_once: set[str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.validation_calls: dict[str, int] = {}
        self.permanently_invalid = permanently_invalid or set()
        self.invalid_once = invalid_once or set()

    async def call(self, tool_name: str, arguments: dict) -> dict:
        self.calls.append((tool_name, arguments))
        if tool_name == "get_server_status":
            return {"overall": "ready", "warnings": []}
        if tool_name == "validate_extraction":
            path = arguments["file_path"]
            self.validation_calls[path] = self.validation_calls.get(path, 0) + 1
            invalid = any(name in path for name in self.permanently_invalid) or (
                self.validation_calls[path] == 1
                and any(name in path for name in self.invalid_once)
            )
            if invalid:
                return {"status": "invalid", "errors": ["relationship endpoint is missing"]}
            return {"status": "success", "valid": True}
        if tool_name == "ingest_from_file":
            return {"status": "success", "file_path": arguments["file_path"]}
        if tool_name == "query_graph_tool":
            return {
                "status": "success",
                "content": "PRECISO graph context",
                "raw_data": {"text_chunks": [{"chunk_id": "zoox.md#chunk_001"}]},
            }
        raise AssertionError(f"unexpected tool {tool_name}")


class GraphExtractor:
    configured = True

    def __init__(self) -> None:
        self.extracted: list[str] = []
        self.repaired: list[str] = []
        self.repair_errors: list[list[str]] = []
        self.answer_contexts: list[dict] = []

    def status(self) -> dict:
        return {"provider": "test", "configured": True, "model": "test"}

    async def extract_document(self, document: dict, **_: object) -> dict:
        self.extracted.append(document["name"])
        return {
            "status": "success",
            "payload": {
                "document_id": "ignored-by-agent",
                "file_path": document["name"],
                "chunks": [{"chunk_id": f"{document['name']}#chunk_001", "content": document["content"]}],
                "entities": [
                    {
                        "entity_name": "component:panasonic-energy:2170-lithium-ion-cell",
                        "entity_type": "COMPONENT",
                        "description": "A documented cell.",
                        "source_id": f"{document['name']}#chunk_001",
                        "file_path": document["name"],
                    }
                ],
                "relationships": [
                    {
                        "src_id": "company:panasonic-energy",
                        "tgt_id": "component:panasonic-energy:2170-lithium-ion-cell",
                        "keywords": "MANUFACTURES",
                        "description": "The source incorrectly attached this to a company.",
                        "source_id": f"{document['name']}#chunk_001",
                        "file_path": document["name"],
                    }
                ],
            },
        }

    async def repair_document(self, document: dict, extraction: dict, errors: list[str], **_: object) -> dict:
        self.repaired.append(document["name"])
        self.repair_errors.append(errors)
        return {
            "status": "success",
            "patch": {
                "operation": "replace_relationship",
                "match": {
                    "src_id": "company:panasonic-energy",
                    "tgt_id": "component:panasonic-energy:2170-lithium-ion-cell",
                    "keywords": "MANUFACTURES",
                },
                "replacement": {"src_id": "facility:panasonic-energy:kansas"},
            },
        }

    async def answer(self, question: str, context: dict) -> dict:
        self.answer_contexts.append(context)
        return {"status": "success", "answer": f"Grounded answer for {question}"}


async def make_runtime(tmp_path: Path, *, permanently_invalid: set[str] | None = None):
    backend = GraphBackend(permanently_invalid=permanently_invalid)
    extractor = GraphExtractor()
    checkpointer_context = AsyncSqliteSaver.from_conn_string(str(tmp_path / "runs.sqlite"))
    checkpointer = await checkpointer_context.__aenter__()
    await checkpointer.setup()
    runtime = SupplyAgentRuntime(
        AgentDependencies(
            application=SupplyChainApplication(backend),
            extractor=extractor,
            registry={"entities": []},
            artifacts=ExtractionArtifactStore(tmp_path / "extractions"),
        ),
        checkpointer,
    )
    return runtime, backend, extractor, checkpointer_context


def source(name: str, content: str = "documented fact") -> dict:
    return {"source_id": name.replace(".", "-"), "name": name, "content": content, "extension": ".md"}


@pytest.mark.asyncio
async def test_approval_interrupt_precedes_ingestion_and_resumes_same_thread(tmp_path: Path) -> None:
    runtime, backend, extractor, checkpoint_context = await make_runtime(tmp_path)
    try:
        first = await runtime.run(
            "conversation:one",
            {
                "conversation_id": "conversation:one",
                "run_id": "run-one",
                "user_query": "Which products depend on this?",
                "snapshot_effective_date": "2026-09-07",
                "uploaded_sources": [source("panasonic.md")],
            },
        )
        assert first.status == "awaiting_approval"
        assert not any(tool == "ingest_from_file" for tool, _ in backend.calls)

        second = await runtime.resume("conversation:one", approved=True)
        assert second.status == "completed"
        assert second.thread_id == first.thread_id == "conversation:one"
        assert second.state["final_answer"] == "Grounded answer for Which products depend on this?"
        assert extractor.answer_contexts == [second.state["query_result"]]
        assert [tool for tool, _ in backend.calls] == [
            "get_server_status",
            "validate_extraction",
            "ingest_from_file",
            "query_graph_tool",
        ]
        assert "approval.required" in [event["type"] for event in second.state["events"]]
    finally:
        await checkpoint_context.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_three_sources_create_three_independent_artifacts_and_shared_ids(tmp_path: Path) -> None:
    runtime, backend, _, checkpoint_context = await make_runtime(tmp_path)
    try:
        sources = [source("01_panasonic_kansas_factory.md"), source("02_harbinger_2170_cells.md"), source("03_zoox_2170_cells.md")]
        paused = await runtime.run(
            "conversation:three",
            {
                "conversation_id": "conversation:three",
                "run_id": "run-three",
                "user_query": "What depends on the Panasonic cell?",
                "snapshot_effective_date": "2026-09-07",
                "uploaded_sources": sources,
            },
        )
        assert paused.status == "awaiting_approval"
        results = paused.state["extraction_results"]
        assert len(results) == 3
        assert all("bundle:" not in result["payload"]["document_id"] for result in results.values())
        assert {result["artifact_name"] for result in results.values()} == {
            "01_panasonic_kansas_factory_extracted.json",
            "02_harbinger_2170_cells_extracted.json",
            "03_zoox_2170_cells_extracted.json",
        }
        ids = {
            entity["entity_name"]
            for result in results.values()
            for entity in result["payload"]["entities"]
        }
        assert ids == {"component:panasonic-energy:2170-lithium-ion-cell"}
        done = await runtime.resume("conversation:three", approved=True)
        assert len([tool for tool, _ in backend.calls if tool == "ingest_from_file"]) == 3
        assert len(done.state["processed_source_ids"]) == 3
    finally:
        await checkpoint_context.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_validation_failure_is_isolated_and_repairs_are_bounded(tmp_path: Path) -> None:
    runtime, backend, extractor, checkpoint_context = await make_runtime(tmp_path, permanently_invalid={"bad"})
    try:
        paused = await runtime.run(
            "conversation:failure",
            {
                "conversation_id": "conversation:failure",
                "run_id": "run-failure",
                "user_query": "What is persisted?",
                "snapshot_effective_date": "2026-09-07",
                "uploaded_sources": [source("good.md"), source("bad.md")],
            },
        )
        assert paused.status == "awaiting_approval"
        assert extractor.repaired == ["bad.md", "bad.md"]
        bad_path = next(path for path in backend.validation_calls if "bad" in path)
        assert backend.validation_calls[bad_path] == 3
        done = await runtime.resume("conversation:failure", approved=True)
        ingested = [path for tool, args in backend.calls if tool == "ingest_from_file" for path in [args["file_path"]]]
        assert len(ingested) == 1 and "good" in ingested[0]
        assert done.state["validation_results"]["bad-md"]["status"] == "validation_failed"
    finally:
        await checkpoint_context.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_repair_edits_one_artifact_and_revalidates_before_approval(tmp_path: Path) -> None:
    runtime, backend, extractor, checkpoint_context = await make_runtime(tmp_path)
    backend.invalid_once = {"bad"}
    try:
        paused = await runtime.run(
            "conversation:surgical",
            {
                "conversation_id": "conversation:surgical",
                "run_id": "run-surgical",
                "user_query": "What is persisted?",
                "snapshot_effective_date": "2026-09-07",
                "uploaded_sources": [source("good.md"), source("bad.md")],
            },
        )
        assert paused.status == "awaiting_approval"
        bad_path = next(path for path in backend.validation_calls if "bad" in path)
        assert backend.validation_calls[bad_path] == 2
        assert extractor.repair_errors == [["relationship endpoint is missing"]]
        assert not any(tool == "ingest_from_file" for tool, _ in backend.calls)

        good = paused.state["extraction_results"]["good-md"]["payload"]
        bad = paused.state["extraction_results"]["bad-md"]["payload"]
        assert good["relationships"][0]["src_id"] == "company:panasonic-energy"
        assert bad["relationships"][0]["src_id"] == "facility:panasonic-energy:kansas"
        assert paused.state["extraction_results"]["bad-md"]["artifact_path"] == bad_path
        event_types = [event["type"] for event in paused.state["events"]]
        assert event_types.count("extraction.edit.completed") == 1
        assert "extraction.patch.generated" in event_types
        assert "extraction.revalidation.completed" in event_types
        assert paused.state["repair_history"][0]["validation_errors"] == [
            "relationship endpoint is missing"
        ]
        assert paused.state["repair_history"][0]["operation"] == "replace_relationship"

        completed = await runtime.resume("conversation:surgical", approved=True)
        assert completed.status == "completed"
        assert len([tool for tool, _ in backend.calls if tool == "ingest_from_file"]) == 2
    finally:
        await checkpoint_context.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_query_only_skips_extraction_and_reuses_ingested_source(tmp_path: Path) -> None:
    runtime, backend, extractor, checkpoint_context = await make_runtime(tmp_path)
    try:
        await runtime.run(
            "conversation:reuse",
            {
                "conversation_id": "conversation:reuse",
                "run_id": "run-reuse",
                "user_query": "Build the graph",
                "snapshot_effective_date": "2026-09-07",
                "uploaded_sources": [source("source.md")],
            },
        )
        await runtime.resume("conversation:reuse", approved=True)
        extracted_count = len(extractor.extracted)
        second = await runtime.run(
            "conversation:reuse",
            {
                "conversation_id": "conversation:reuse",
                "run_id": "run-query",
                "user_query": "What is connected?",
                "snapshot_effective_date": "2026-09-07",
                "messages": [{"role": "user", "content": "What is connected?"}],
            },
        )
        assert second.status == "completed"
        assert len(extractor.extracted) == extracted_count
        assert second.state["intent"] == "graph_query"
        assert [tool for tool, _ in backend.calls].count("query_graph_tool") == 1
    finally:
        await checkpoint_context.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_extraction_only_instruction_does_not_become_a_graph_query(tmp_path: Path) -> None:
    runtime, backend, extractor, checkpoint_context = await make_runtime(tmp_path)
    try:
        paused = await runtime.run(
            "conversation:extract-only",
            {
                "conversation_id": "conversation:extract-only",
                "run_id": "run-extract-only",
                "user_query": "Extract these documents and prepare them for review.",
                "snapshot_effective_date": "2026-09-07",
                "uploaded_sources": [source("source.md")],
            },
        )
        assert paused.status == "awaiting_approval"

        completed = await runtime.resume("conversation:extract-only", approved=True)

        assert completed.state["intent"] == "new_sources"
        assert not any(tool == "query_graph_tool" for tool, _ in backend.calls)
        assert extractor.answer_contexts == []
        assert completed.state["final_answer"] == (
            "The source artifacts were approved and ingested into PRECISO; "
            "no graph question was requested."
        )
    finally:
        await checkpoint_context.__aexit__(None, None, None)
