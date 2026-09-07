"""The explicit Supply Center orchestration graph.

This module coordinates the application-owned experience. It deliberately
does not validate ontology, retrieve vectors, merge entities, or maintain a
graph; those operations remain PRECISO MCP calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from preciso_supply_agent.agent.artifacts import ExtractionArtifactStore, ExtractionPatch
from preciso_supply_agent.agent.state import (
    SupplyAgentState,
    execution_event,
)
from preciso_supply_agent.application import SupplyChainApplication
from preciso_supply_agent.documents.readers import read_source
from preciso_supply_agent.extraction import ExtractionError

MAX_REPAIR_ATTEMPTS = 2


@dataclass(frozen=True)
class AgentDependencies:
    application: SupplyChainApplication
    extractor: Any
    registry: dict[str, Any]
    artifacts: ExtractionArtifactStore


def _events(state: SupplyAgentState, *events: dict[str, Any]) -> dict[str, Any]:
    return {"events": list(events)}


def _source_by_id(state: SupplyAgentState) -> dict[str, dict[str, Any]]:
    return {str(source["source_id"]): source for source in state.get("uploaded_sources", [])}


def _is_success(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    status = str(result.get("status", "")).lower()
    if result.get("valid") is False or result.get("ok") is False:
        return False
    if any(result.get(key) for key in ("errors", "validation_errors", "error")):
        return False
    return status in {"success", "ok", "valid", "validated", "ready", "complete"} or (
        not status and result.get("valid") is True
    )


def _validation_errors(result: Any) -> list[str]:
    if not isinstance(result, dict):
        return ["PRECISO returned a non-object validation result"]
    errors: Any = (
        result.get("errors")
        or result.get("validation_errors")
        or result.get("issues")
        or result.get("error")
    )
    if errors is None:
        return ["PRECISO rejected the extraction without a detailed error"]
    if isinstance(errors, list):
        return [str(error) for error in errors]
    return [str(errors)]


def _append_error(
    errors: dict[str, list[str]], source_id: str, messages: list[str]
) -> dict[str, list[str]]:
    updated = {key: list(value) for key, value in errors.items()}
    updated[source_id] = [*updated.get(source_id, []), *messages]
    return updated


def _is_extraction_only_request(query: str) -> bool:
    """Recognize UI instructions that request preparation, not graph analysis."""

    normalized = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    if not normalized:
        return True
    tokens = set(normalized.split())
    extraction_words = {"extract", "prepare", "review", "ingest", "ingested"}
    extraction_phrases = ("build the graph", "create the graph")
    question_words = {
        "what",
        "which",
        "who",
        "where",
        "when",
        "why",
        "how",
        "does",
        "is",
        "are",
        "can",
        "show",
        "depends",
        "exposed",
        "query",
        "trace",
    }
    has_extraction_language = bool(tokens & extraction_words) or any(
        phrase in normalized for phrase in extraction_phrases
    )
    has_question_language = bool(tokens & question_words) or "tell me" in normalized
    return has_extraction_language and not has_question_language


def _intent(state: SupplyAgentState) -> str:
    query = state.get("user_query", "").strip()
    statuses = state.get("source_statuses", {})
    extractions = state.get("extraction_results", {})
    ingestions = state.get("ingestion_results", {})
    has_pending = any(
        source_id not in ingestions
        and statuses.get(source_id) != "ingested"
        and source_id not in extractions
        for source_id in _source_by_id(state)
    )
    has_reviewable = any(
        source_id not in ingestions
        and validation.get("status") in {"valid", "validated", "success"}
        for source_id, validation in state.get("validation_results", {}).items()
    )
    if has_pending or has_reviewable:
        return (
            "new_sources"
            if _is_extraction_only_request(query)
            else "new_sources_and_query"
        )
    return "graph_query" if query else "new_sources"


def _status_event(
    state: SupplyAgentState, event_type: str, *, node: str, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return execution_event(event_type, run_id=state.get("run_id"), node=node, data=data)


def create_supply_graph(
    dependencies: AgentDependencies, checkpointer: BaseCheckpointSaver
):
    """Build and compile the V1 Supply Center StateGraph."""

    async def initialize_run(state: SupplyAgentState) -> dict[str, Any]:
        run_id = state.get("run_id") or __import__("uuid").uuid4().hex
        conversation_id = state.get("conversation_id") or "conversation:unassigned"
        return {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "errors": list(state.get("errors", [])),
            "events": [
                execution_event("run.started", run_id=run_id, node="initialize_run")
            ],
        }

    async def check_preciso_status(state: SupplyAgentState) -> dict[str, Any]:
        node = "check_preciso_status"
        started = _status_event(state, "preciso.status.started", node=node)
        try:
            status = await dependencies.application.status()
        except Exception as exc:  # noqa: BLE001 - a node must preserve partial per-source state
            message = f"PRECISO is unavailable: {exc}"
            return {
                "preciso_status": {"overall": "error", "error": message},
                "errors": [*state.get("errors", []), message],
                "events": [
                    started,
                    _status_event(state, "preciso.status.failed", node=node, data={"error": message}),
                ],
            }
        if not isinstance(status, dict) or status.get("overall") not in {"ready", "degraded"}:
            message = "PRECISO returned an unusable server status"
            return {
                "preciso_status": {"overall": "error", "raw": status, "error": message},
                "errors": [*state.get("errors", []), message],
                "events": [
                    started,
                    _status_event(state, "preciso.status.failed", node=node, data={"error": message}),
                ],
            }
        warnings = status.get("warnings", []) if isinstance(status, dict) else []
        return {
            "preciso_status": status,
            "errors": [*state.get("errors", []), *[str(warning) for warning in warnings]],
            "events": [
                started,
                _status_event(
                    state,
                    "preciso.status.completed",
                    node=node,
                    data={"overall": status.get("overall") if isinstance(status, dict) else None},
                ),
            ],
        }

    async def understand_request(state: SupplyAgentState) -> dict[str, Any]:
        intent = _intent(state)
        return {
            "intent": intent,
            "events": [
                _status_event(
                    state,
                    "request.understood",
                    node="understand_request",
                    data={"intent": intent},
                )
            ],
        }

    async def prepare_sources(state: SupplyAgentState) -> dict[str, Any]:
        statuses = dict(state.get("source_statuses", {}))
        processed = list(state.get("processed_source_ids", []))
        sources = []
        extraction_results = state.get("extraction_results", {})
        ingestion_results = state.get("ingestion_results", {})
        to_process = []
        for source in state.get("uploaded_sources", []):
            source = dict(source)
            source_id = str(source["source_id"])
            status = statuses.get(source_id, "uploaded")
            if source_id in ingestion_results or ingestion_results.get(source_id, {}).get("status") == "success":
                status = "ingested"
                if source_id not in processed:
                    processed.append(source_id)
            elif source_id in extraction_results and status == "uploaded":
                status = "extracted"
            source["status"] = status
            sources.append(source)
            statuses[source_id] = status
            if status not in {"ingested", "validated", "awaiting_approval"} and source_id not in extraction_results:
                to_process.append(source_id)

        event = _status_event(
            state,
            "sources.prepared",
            node="prepare_sources",
            data={"source_count": len(sources), "to_process": to_process},
        )
        return {
            "uploaded_sources": sources,
            "source_statuses": statuses,
            "sources_to_process": to_process,
            "processed_source_ids": processed,
            "events": [event],
        }

    async def read_sources(state: SupplyAgentState) -> dict[str, Any]:
        source_map = _source_by_id(state)
        read_sources = dict(state.get("read_sources", {}))
        statuses = dict(state.get("source_statuses", {}))
        errors = {key: list(value) for key, value in state.get("extraction_errors", {}).items()}
        events = []
        for source_id in state.get("sources_to_process", []):
            source = source_map[source_id]
            events.append(
                execution_event(
                    "source.read.started",
                    run_id=state.get("run_id"),
                    node="read_sources",
                    source_id=source_id,
                    source_name=source["name"],
                )
            )
            statuses[source_id] = "reading"
            try:
                read_sources[source_id] = read_source(source)
                statuses[source_id] = "uploaded"
                events.append(
                    execution_event(
                        "source.read.completed",
                        run_id=state.get("run_id"),
                        node="read_sources",
                        source_id=source_id,
                        source_name=source["name"],
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate unreadable sources
                message = f"Could not read {source['name']}: {exc}"
                statuses[source_id] = "failed"
                errors = _append_error(errors, source_id, [message])
                events.append(
                    execution_event(
                        "source.read.failed",
                        run_id=state.get("run_id"),
                        node="read_sources",
                        source_id=source_id,
                        source_name=source["name"],
                        data={"error": message},
                    )
                )
        return {"read_sources": read_sources, "source_statuses": statuses, "extraction_errors": errors, "events": events}

    async def extract_sources(state: SupplyAgentState) -> dict[str, Any]:
        source_map = _source_by_id(state)
        results = dict(state.get("extraction_results", {}))
        attempts = dict(state.get("extraction_attempts", {}))
        statuses = dict(state.get("source_statuses", {}))
        errors = {key: list(value) for key, value in state.get("extraction_errors", {}).items()}
        events = []
        for source_id in state.get("sources_to_process", []):
            if source_id not in state.get("read_sources", {}):
                continue
            source = source_map[source_id]
            read_source_record = state.get("read_sources", {}).get(source_id, {})
            document = {
                "name": source["name"],
                "content": read_source_record.get("content", ""),
                "source_id": source_id,
            }
            if not document["content"]:
                message = f"Could not extract {source['name']}: source content is unavailable"
                statuses[source_id] = "failed"
                errors = _append_error(errors, source_id, [message])
                continue
            events.append(
                execution_event(
                    "extraction.started",
                    run_id=state.get("run_id"),
                    node="extract_sources",
                    source_id=source_id,
                    source_name=source["name"],
                )
            )
            attempts[source_id] = attempts.get(source_id, 0) + 1
            try:
                if hasattr(dependencies.extractor, "extract_document"):
                    extraction = await dependencies.extractor.extract_document(
                        document,
                        snapshot_effective_date=state.get("snapshot_effective_date", ""),
                        registry=dependencies.registry,
                    )
                else:
                    extraction = await dependencies.extractor.extract(
                        [document],
                        snapshot_effective_date=state.get("snapshot_effective_date", ""),
                        registry=dependencies.registry,
                    )
                payload = extraction.get("payload", extraction) if isinstance(extraction, dict) else extraction
                if not isinstance(payload, dict):
                    raise ExtractionError("Extractor returned a non-object payload")
                payload = dict(payload)
                payload["document_id"] = f"document:{source_id}"
                payload["file_path"] = source["name"]
                payload["snapshot_effective_date"] = state.get("snapshot_effective_date", "")
                artifact = dependencies.artifacts.write(source["name"], source_id, payload)
                results[source_id] = {
                    "source_id": source_id,
                    "source_name": source["name"],
                    "payload": payload,
                    **artifact,
                    "status": "extracted",
                }
                statuses[source_id] = "extracted"
                events.extend(
                    [
                        execution_event(
                            "extraction.completed",
                            run_id=state.get("run_id"),
                            node="extract_sources",
                            source_id=source_id,
                            source_name=source["name"],
                            data={
                                "entities": len(payload.get("entities", [])),
                                "relationships": len(payload.get("relationships", [])),
                            },
                        ),
                        execution_event(
                            "extraction.artifact_written",
                            run_id=state.get("run_id"),
                            node="extract_sources",
                            source_id=source_id,
                            source_name=source["name"],
                            data={"artifact_name": artifact["artifact_name"]},
                        ),
                    ]
                )
            except Exception as exc:  # noqa: BLE001 - isolate model failures per source
                message = f"Could not extract {source['name']}: {exc}"
                statuses[source_id] = "failed"
                errors = _append_error(errors, source_id, [message])
                events.append(
                    execution_event(
                        "extraction.failed",
                        run_id=state.get("run_id"),
                        node="extract_sources",
                        source_id=source_id,
                        source_name=source["name"],
                        data={"error": message},
                    )
                )
        return {"extraction_results": results, "extraction_attempts": attempts, "source_statuses": statuses, "extraction_errors": errors, "events": events}

    async def validate_extractions(state: SupplyAgentState) -> dict[str, Any]:
        results = dict(state.get("validation_results", {}))
        statuses = dict(state.get("source_statuses", {}))
        errors = {key: list(value) for key, value in state.get("extraction_errors", {}).items()}
        events = []
        valid_ids = []
        for source_id, extraction in state.get("extraction_results", {}).items():
            if source_id in state.get("ingestion_results", {}):
                continue
            source_name = extraction.get("source_name", source_id)
            is_revalidation = state.get("extraction_attempts", {}).get(source_id, 0) > 1
            events.append(
                execution_event(
                    "validation.started",
                    run_id=state.get("run_id"),
                    node="validate_extractions",
                    source_id=source_id,
                    source_name=source_name,
                )
            )
            if is_revalidation:
                events.append(
                    execution_event(
                        "extraction.revalidation.started",
                        run_id=state.get("run_id"),
                        node="validate_extractions",
                        source_id=source_id,
                        source_name=source_name,
                        data={"attempt": state.get("extraction_attempts", {}).get(source_id)},
                    )
                )
            try:
                raw = await dependencies.application.validate_extraction(extraction["artifact_path"])
                if _is_success(raw):
                    result = {"source_id": source_id, "status": "valid", "raw": raw}
                    statuses[source_id] = "validated"
                    valid_ids.append(source_id)
                    events.append(
                        execution_event(
                            "validation.completed",
                            run_id=state.get("run_id"),
                            node="validate_extractions",
                            source_id=source_id,
                            source_name=source_name,
                            data={"status": "valid"},
                        )
                    )
                    if is_revalidation:
                        events.append(
                            execution_event(
                                "extraction.revalidation.completed",
                                run_id=state.get("run_id"),
                                node="validate_extractions",
                                source_id=source_id,
                                source_name=source_name,
                                data={"status": "valid"},
                            )
                        )
                else:
                    validation_errors = _validation_errors(raw)
                    result = {
                        "source_id": source_id,
                        "status": "validation_failed",
                        "errors": validation_errors,
                        "raw": raw if isinstance(raw, dict) else {"result": raw},
                    }
                    statuses[source_id] = "validation_failed"
                    errors = _append_error(errors, source_id, validation_errors)
                    events.append(
                        execution_event(
                            "validation.failed",
                            run_id=state.get("run_id"),
                            node="validate_extractions",
                            source_id=source_id,
                            source_name=source_name,
                            data={"errors": validation_errors},
                        )
                    )
                    events.append(
                        execution_event(
                            "extraction.validation_failed",
                            run_id=state.get("run_id"),
                            node="validate_extractions",
                            source_id=source_id,
                            source_name=source_name,
                            data={"errors": validation_errors},
                        )
                    )
                    if is_revalidation:
                        events.append(
                            execution_event(
                                "extraction.revalidation.completed",
                                run_id=state.get("run_id"),
                                node="validate_extractions",
                                source_id=source_id,
                                source_name=source_name,
                                data={"status": "invalid", "errors": validation_errors},
                            )
                        )
                results[source_id] = result
            except Exception as exc:  # noqa: BLE001 - preserve validation failures in state
                message = f"PRECISO validation failed for {source_name}: {exc}"
                statuses[source_id] = "validation_failed"
                errors = _append_error(errors, source_id, [message])
                results[source_id] = {"source_id": source_id, "status": "validation_failed", "errors": [message]}
                events.append(
                    execution_event(
                        "validation.failed",
                        run_id=state.get("run_id"),
                        node="validate_extractions",
                        source_id=source_id,
                        source_name=source_name,
                        data={"errors": [message]},
                    )
                )
                events.append(
                    execution_event(
                        "extraction.validation_failed",
                        run_id=state.get("run_id"),
                        node="validate_extractions",
                        source_id=source_id,
                        source_name=source_name,
                        data={"errors": [message]},
                    )
                )
                if is_revalidation:
                    events.append(
                        execution_event(
                            "extraction.revalidation.completed",
                            run_id=state.get("run_id"),
                            node="validate_extractions",
                            source_id=source_id,
                            source_name=source_name,
                            data={"status": "invalid", "errors": [message]},
                        )
                    )
        if valid_ids:
            for source_id in valid_ids:
                statuses[source_id] = "awaiting_approval"
            events.append(
                _status_event(
                    state,
                    "approval.required",
                    node="approval_gate",
                    data={"source_ids": valid_ids},
                )
            )
        return {
            "validation_results": results,
            "source_statuses": statuses,
            "extraction_errors": errors,
            "awaiting_approval": bool(valid_ids),
            "events": events,
        }

    async def repair_extractions(state: SupplyAgentState) -> dict[str, Any]:
        source_map = _source_by_id(state)
        results = dict(state.get("extraction_results", {}))
        attempts = dict(state.get("extraction_attempts", {}))
        errors = {key: list(value) for key, value in state.get("extraction_errors", {}).items()}
        statuses = dict(state.get("source_statuses", {}))
        repair_history = list(state.get("repair_history", []))
        events = []
        for source_id, validation in state.get("validation_results", {}).items():
            if validation.get("status") != "validation_failed" or attempts.get(source_id, 0) >= MAX_REPAIR_ATTEMPTS + 1:
                continue
            source = source_map.get(source_id)
            extraction = results.get(source_id)
            if not source or not extraction:
                continue
            attempt = attempts.get(source_id, 0) + 1
            events.append(
                execution_event(
                    "extraction.repair.started",
                    run_id=state.get("run_id"),
                    node="repair_extractions",
                    source_id=source_id,
                    source_name=source["name"],
                    data={"attempt": attempt},
                )
            )
            attempts[source_id] = attempt
            patch: ExtractionPatch | None = None
            edit_started = False
            edit_succeeded = False
            try:
                if not hasattr(dependencies.extractor, "repair_document"):
                    raise ExtractionError("Configured extractor does not support bounded repair")
                repaired = await dependencies.extractor.repair_document(
                    {
                        "name": source["name"],
                        "content": state.get("read_sources", {}).get(source_id, {}).get("content", ""),
                        "source_id": source_id,
                    },
                    extraction["payload"],
                    validation.get("errors", []),
                    snapshot_effective_date=state.get("snapshot_effective_date", ""),
                    registry=dependencies.registry,
                )
                raw_patch = repaired.get("patch", repaired) if isinstance(repaired, dict) else repaired
                if not isinstance(raw_patch, dict):
                    raise ExtractionError("Repair returned a non-object structured patch")
                patch = ExtractionPatch.from_payload(raw_patch)
                events.append(
                    execution_event(
                        "extraction.patch.generated",
                        run_id=state.get("run_id"),
                        node="repair_extractions",
                        source_id=source_id,
                        source_name=source["name"],
                        data={
                            "attempt": attempt,
                            "operation": patch.operation,
                            "target": patch.match,
                        },
                    )
                )
                events.append(
                    execution_event(
                        "extraction.edit.started",
                        run_id=state.get("run_id"),
                        node="repair_extractions",
                        source_id=source_id,
                        source_name=source["name"],
                        data={"attempt": attempt, "operation": patch.operation},
                    )
                )
                edit_started = True
                edit_result = dependencies.artifacts.edit_extraction(
                    extraction["artifact_path"], patch
                )
                if edit_result.get("status") != "success":
                    raise ExtractionError(
                        f"Structured edit failed: {edit_result.get('reason', 'unknown_error')}"
                    )
                edit_succeeded = True
                events.append(
                    execution_event(
                        "extraction.edit.completed",
                        run_id=state.get("run_id"),
                        node="repair_extractions",
                        source_id=source_id,
                        source_name=source["name"],
                        data={
                            "attempt": attempt,
                            "operation": patch.operation,
                            "changed": edit_result.get("changed", 0),
                        },
                    )
                )
                payload = dependencies.artifacts.read_payload(extraction["artifact_path"])
                results[source_id] = {
                    **extraction,
                    "payload": payload,
                    "status": "extracted",
                }
                statuses[source_id] = "extracted"
                repair_history.append(
                    {
                        "attempt": attempt,
                        "timestamp": events[-1]["timestamp"],
                        "source_id": source_id,
                        "source_name": source["name"],
                        "validation_errors": list(validation.get("errors", [])),
                        "operation": patch.operation,
                        "target": dict(patch.match),
                        "status": "success",
                    }
                )
                events.append(
                    execution_event(
                        "extraction.repair.completed",
                        run_id=state.get("run_id"),
                        node="repair_extractions",
                        source_id=source_id,
                        source_name=source["name"],
                        data={
                            "attempt": attempts[source_id],
                            "operation": patch.operation,
                            "target": patch.match,
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001 - keep repair bounded and per source
                message = f"Could not repair {source['name']}: {exc}"
                errors = _append_error(errors, source_id, [message])
                statuses[source_id] = "validation_failed"
                if edit_started and not edit_succeeded and patch is not None:
                    events.append(
                        execution_event(
                            "extraction.edit.failed",
                            run_id=state.get("run_id"),
                            node="repair_extractions",
                            source_id=source_id,
                            source_name=source["name"],
                            data={
                                "attempt": attempt,
                                "operation": patch.operation,
                                "error": message,
                            },
                        )
                    )
                repair_history.append(
                    {
                        "attempt": attempt,
                        "timestamp": execution_event("repair.failed")["timestamp"],
                        "source_id": source_id,
                        "source_name": source["name"],
                        "validation_errors": list(validation.get("errors", [])),
                        "status": "failed",
                        "error": message,
                    }
                )
                events.append(
                    execution_event(
                        "extraction.repair.failed",
                        run_id=state.get("run_id"),
                        node="repair_extractions",
                        source_id=source_id,
                        source_name=source["name"],
                        data={"error": message, "attempt": attempts[source_id]},
                    )
                )
        return {
            "extraction_results": results,
            "extraction_attempts": attempts,
            "source_statuses": statuses,
            "extraction_errors": errors,
            "repair_history": repair_history,
            "events": events,
        }

    async def approval_gate(state: SupplyAgentState) -> dict[str, Any]:
        valid_ids = [
            source_id
            for source_id, validation in state.get("validation_results", {}).items()
            if validation.get("status") == "valid"
            and source_id not in state.get("ingestion_results", {})
        ]
        summaries = []
        for source_id in valid_ids:
            extraction = state.get("extraction_results", {}).get(source_id, {})
            payload = extraction.get("payload", {})
            summaries.append(
                {
                    "source_id": source_id,
                    "source_name": extraction.get("source_name", source_id),
                    "artifact_name": extraction.get("artifact_name"),
                    "entities": len(payload.get("entities", [])),
                    "relationships": len(payload.get("relationships", [])),
                    "status": "validated",
                }
            )
        decision = interrupt(
            {
                "type": "approval_required",
                "message": "Review validated extraction artifacts before additive graph ingestion.",
                "sources": summaries,
            }
        )
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        approved_ids = valid_ids if approved else []
        rejected_ids = [] if approved else valid_ids
        statuses = dict(state.get("source_statuses", {}))
        for source_id in rejected_ids:
            statuses[source_id] = "failed"
        return {
            "awaiting_approval": False,
            "approved_extraction_ids": approved_ids,
            "rejected_extraction_ids": rejected_ids,
            "source_statuses": statuses,
            "events": [
                _status_event(
                    state,
                    "approval.received",
                    node="approval_gate",
                    data={"approved": approved, "source_ids": approved_ids},
                )
            ],
        }

    async def ingest_extractions(state: SupplyAgentState) -> dict[str, Any]:
        results = dict(state.get("ingestion_results", {}))
        statuses = dict(state.get("source_statuses", {}))
        processed = list(state.get("processed_source_ids", []))
        events = []
        for source_id in state.get("approved_extraction_ids", []):
            extraction = state.get("extraction_results", {}).get(source_id)
            if not extraction:
                continue
            source_name = extraction.get("source_name", source_id)
            events.append(
                execution_event(
                    "ingestion.started",
                    run_id=state.get("run_id"),
                    node="ingest_extractions",
                    source_id=source_id,
                    source_name=source_name,
                )
            )
            try:
                raw = await dependencies.application.ingest_extraction_file(extraction["artifact_path"])
                if not _is_success(raw):
                    raise RuntimeError(str(raw.get("errors") or raw.get("message") or raw))
                results[source_id] = {
                    "source_id": source_id,
                    "source_name": source_name,
                    "status": "success",
                    "raw": raw,
                }
                statuses[source_id] = "ingested"
                if source_id not in processed:
                    processed.append(source_id)
                events.append(
                    execution_event(
                        "ingestion.completed",
                        run_id=state.get("run_id"),
                        node="ingest_extractions",
                        source_id=source_id,
                        source_name=source_name,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - keep other approved sources progressing
                message = f"PRECISO ingestion failed for {source_name}: {exc}"
                results[source_id] = {"source_id": source_id, "source_name": source_name, "status": "failed", "error": message}
                statuses[source_id] = "failed"
                events.append(
                    execution_event(
                        "ingestion.failed",
                        run_id=state.get("run_id"),
                        node="ingest_extractions",
                        source_id=source_id,
                        source_name=source_name,
                        data={"error": message},
                    )
                )
        return {
            "ingestion_results": results,
            "source_statuses": statuses,
            "processed_source_ids": processed,
            "events": events,
        }

    async def query_preciso(state: SupplyAgentState) -> dict[str, Any]:
        query = state.get("user_query", "").strip()
        if not query or state.get("intent") == "new_sources":
            return {"query_result": {"status": "not_requested"}, "grounded_context": None}
        started = _status_event(state, "graph.query.started", node="query_preciso")
        try:
            result = await dependencies.application.query_graph(query, mode="mix")
            raw_data = result.get("raw_data", {}) if isinstance(result, dict) else {}
            evidence = []
            if isinstance(raw_data, dict):
                for key in ("text_chunks", "references"):
                    value = raw_data.get(key, [])
                    if isinstance(value, list):
                        evidence.extend(item for item in value if isinstance(item, dict))
            return {
                "query_result": result,
                "grounded_context": result,
                "evidence": evidence,
                "events": [
                    started,
                    _status_event(
                        state,
                        "graph.query.completed",
                        node="query_preciso",
                        data={"evidence_count": len(evidence)},
                    ),
                ],
            }
        except Exception as exc:  # noqa: BLE001 - convert backend failure into grounded state
            message = f"PRECISO graph query failed: {exc}"
            return {
                "query_result": {"status": "error", "message": message},
                "grounded_context": None,
                "errors": [*state.get("errors", []), message],
                "events": [
                    started,
                    _status_event(state, "graph.query.failed", node="query_preciso", data={"error": message}),
                ],
            }

    async def synthesize_answer(state: SupplyAgentState) -> dict[str, Any]:
        query = state.get("user_query", "").strip()
        if not query or state.get("intent") == "new_sources":
            if state.get("rejected_extraction_ids"):
                answer = "No graph update was made because the validated extraction was not approved."
            elif any(
                result.get("status") == "success"
                for result in state.get("ingestion_results", {}).values()
            ):
                answer = (
                    "The source artifacts were approved and ingested into PRECISO; "
                    "no graph question was requested."
                )
            elif any(
                result.get("status") in {"valid", "validated", "success"}
                for result in state.get("validation_results", {}).values()
            ):
                answer = "The validated source artifacts are ready for review; no graph question was requested."
            else:
                answer = "The source artifacts could not be validated; no graph update was made."
            return {
                "final_answer": answer,
                "events": [_status_event(state, "answer.completed", node="synthesize_answer")],
            }
        started = _status_event(state, "answer.started", node="synthesize_answer")
        context = state.get("grounded_context") or state.get("query_result") or {}
        try:
            result = await dependencies.extractor.answer(query, context)
            answer = result.get("answer", "") if isinstance(result, dict) else str(result)
            if not answer:
                raise ExtractionError("Claude returned an empty grounded answer")
            return {
                "final_answer": answer,
                "events": [
                    started,
                    _status_event(
                        state,
                        "answer.token",
                        node="synthesize_answer",
                        data={"text": answer, "final": True, "streamed": False},
                    ),
                    _status_event(
                        state,
                        "answer.completed",
                        node="synthesize_answer",
                        data={"grounded": bool(context)},
                    ),
                ],
            }
        except Exception as exc:  # noqa: BLE001 - return an explicit synthesis failure
            message = f"Grounded answer synthesis failed: {exc}"
            return {
                "final_answer": "I could not produce a grounded answer from the available PRECISO evidence.",
                "errors": [*state.get("errors", []), message],
                "events": [
                    started,
                    _status_event(state, "answer.failed", node="synthesize_answer", data={"error": message}),
                ],
            }

    def route_after_status(state: SupplyAgentState) -> str:
        return "failure" if state.get("preciso_status", {}).get("overall") == "error" else "understand_request"

    def route_after_understanding(state: SupplyAgentState) -> str:
        return "prepare_sources" if state.get("intent") in {"new_sources", "new_sources_and_query"} else "query_preciso"

    def route_after_prepare(state: SupplyAgentState) -> str:
        if state.get("intent") == "graph_query":
            return "query_preciso"
        if state.get("sources_to_process"):
            return "read_sources"
        if any(value.get("status") == "valid" for value in state.get("validation_results", {}).values()):
            return "approval_gate"
        return (
            "query_preciso"
            if state.get("intent") == "new_sources_and_query"
            and state.get("user_query", "").strip()
            else "synthesize_answer"
        )

    def route_after_validation(state: SupplyAgentState) -> str:
        for source_id, validation in state.get("validation_results", {}).items():
            if validation.get("status") == "validation_failed" and state.get("extraction_attempts", {}).get(source_id, 0) < MAX_REPAIR_ATTEMPTS + 1:
                return "repair_extractions"
        if any(value.get("status") == "valid" for value in state.get("validation_results", {}).values()):
            return "approval_gate"
        return (
            "query_preciso"
            if state.get("intent") == "new_sources_and_query"
            and state.get("user_query", "").strip()
            else "synthesize_answer"
        )

    def route_after_approval(state: SupplyAgentState) -> str:
        return (
            "ingest_extractions"
            if state.get("approved_extraction_ids")
            else (
                "query_preciso"
                if state.get("intent") == "new_sources_and_query"
                and state.get("user_query", "").strip()
                else "synthesize_answer"
            )
        )

    def route_after_ingestion(state: SupplyAgentState) -> str:
        return "query_preciso" if state.get("intent") == "new_sources_and_query" else "synthesize_answer"

    builder = StateGraph(SupplyAgentState)
    builder.add_node("initialize_run", initialize_run)
    builder.add_node("check_preciso_status", check_preciso_status)
    builder.add_node("understand_request", understand_request)
    builder.add_node("prepare_sources", prepare_sources)
    builder.add_node("read_sources", read_sources)
    builder.add_node("extract_sources", extract_sources)
    builder.add_node("validate_extractions", validate_extractions)
    builder.add_node("repair_extractions", repair_extractions)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("ingest_extractions", ingest_extractions)
    builder.add_node("query_preciso", query_preciso)
    builder.add_node("synthesize_answer", synthesize_answer)
    builder.add_node("failure", lambda state: {"final_answer": "PRECISO is unavailable; no graph update was attempted."})

    builder.add_edge(START, "initialize_run")
    builder.add_edge("initialize_run", "check_preciso_status")
    builder.add_conditional_edges("check_preciso_status", route_after_status)
    builder.add_conditional_edges("understand_request", route_after_understanding)
    builder.add_conditional_edges("prepare_sources", route_after_prepare)
    builder.add_edge("read_sources", "extract_sources")
    builder.add_edge("extract_sources", "validate_extractions")
    builder.add_conditional_edges("validate_extractions", route_after_validation)
    builder.add_edge("repair_extractions", "validate_extractions")
    builder.add_conditional_edges("approval_gate", route_after_approval)
    builder.add_conditional_edges("ingest_extractions", route_after_ingestion)
    builder.add_edge("query_preciso", "synthesize_answer")
    builder.add_edge("synthesize_answer", END)
    builder.add_edge("failure", END)
    return builder.compile(checkpointer=checkpointer)
