"""Typed state carried by the Supply Center LangGraph."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages


Intent = Literal["new_sources", "graph_query", "new_sources_and_query"]
SourceStatus = Literal[
    "uploaded",
    "reading",
    "extracted",
    "validation_failed",
    "validated",
    "awaiting_approval",
    "ingested",
    "failed",
]


class SourceRecord(TypedDict, total=False):
    source_id: str
    name: str
    content: str
    extension: str
    status: SourceStatus
    metadata: dict[str, Any]
    artifact_path: str
    artifact_name: str


class ExtractionResult(TypedDict, total=False):
    source_id: str
    source_name: str
    payload: dict[str, Any]
    artifact_path: str
    artifact_name: str
    status: str
    error: str


class ValidationResult(TypedDict, total=False):
    source_id: str
    status: str
    errors: list[str]
    raw: dict[str, Any]


class IngestionResult(TypedDict, total=False):
    source_id: str
    source_name: str
    status: str
    raw: dict[str, Any]
    error: str


class SupplyAgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    conversation_id: str
    run_id: str
    user_query: str
    snapshot_effective_date: str

    uploaded_sources: list[SourceRecord]
    sources_to_process: list[str]
    processed_source_ids: list[str]
    source_statuses: dict[str, SourceStatus]
    read_sources: dict[str, dict[str, Any]]

    extraction_results: dict[str, ExtractionResult]
    validation_results: dict[str, ValidationResult]
    extraction_errors: dict[str, list[str]]
    extraction_attempts: dict[str, int]

    awaiting_approval: bool
    approved_extraction_ids: list[str]
    rejected_extraction_ids: list[str]

    ingestion_results: dict[str, IngestionResult]
    preciso_status: dict[str, Any] | None
    query_result: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    grounded_context: dict[str, Any] | None
    final_answer: str | None

    intent: Intent
    errors: list[str]
    events: Annotated[list[dict[str, Any]], add]


def execution_event(
    event_type: str,
    *,
    run_id: str | None = None,
    node: str | None = None,
    source_id: str | None = None,
    source_name: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if run_id:
        event["run_id"] = run_id
    if node:
        event["node"] = node
    if source_id:
        event["source_id"] = source_id
    if source_name:
        event["source_name"] = source_name
    if data:
        event["data"] = data
    return event
