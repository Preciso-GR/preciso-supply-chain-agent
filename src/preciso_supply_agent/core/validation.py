"""Fail-closed validation for reviewed supply-chain extraction payloads."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from typing import Any

from preciso_supply_agent.core.models import (
    ENTITY_TYPES,
    RELATIONSHIP_RULES,
    PreparedPayload,
    relationship_type,
    source_ids,
)


def validate_payload(payload: Any) -> tuple[PreparedPayload | None, list[str]]:
    if not isinstance(payload, dict):
        return None, ["payload must be an object"]

    errors: list[str] = []
    document_id = _required_text(payload, "document_id", errors)
    file_path = str(payload.get("file_path", "unknown_source")).strip() or "unknown_source"
    snapshot_date = str(payload.get("snapshot_effective_date", "")).strip()
    if snapshot_date:
        try:
            if date.fromisoformat(snapshot_date).isoformat() != snapshot_date:
                raise ValueError
        except ValueError:
            errors.append("snapshot_effective_date must use YYYY-MM-DD")

    chunks = _list_field(payload, "chunks", errors)
    entities = _list_field(payload, "entities", errors)
    relationships = _list_field(payload, "relationships", errors)

    chunk_ids: set[str] = set()
    normalized_chunks: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            errors.append(f"chunk at index {index} must be an object")
            continue
        chunk_id = str(chunk.get("chunk_id", "")).strip()
        content = str(chunk.get("content", "")).strip()
        if not chunk_id:
            errors.append(f"chunk at index {index} requires chunk_id")
        elif chunk_id in chunk_ids:
            errors.append(f"duplicate chunk_id `{chunk_id}`")
        else:
            chunk_ids.add(chunk_id)
        if not content:
            errors.append(f"chunk `{chunk_id or index}` has empty content")
        order_value = chunk.get("chunk_order_index", index)
        try:
            order_index = int(order_value)
        except (TypeError, ValueError):
            errors.append(f"chunk `{chunk_id or index}` has invalid chunk_order_index")
            order_index = index
        normalized_chunks.append(
            {
                **chunk,
                "chunk_id": chunk_id,
                "content": content,
                "file_path": str(chunk.get("file_path", file_path)).strip() or file_path,
                "chunk_order_index": order_index,
            }
        )

    entity_types: dict[str, str] = {}
    normalized_entities: list[dict[str, Any]] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            errors.append(f"entity at index {index} must be an object")
            continue
        entity_id = str(entity.get("entity_name", "")).strip()
        entity_type = str(entity.get("entity_type", "")).strip().upper()
        description = str(entity.get("description", "")).strip()
        if not entity_id:
            errors.append(f"entity at index {index} requires entity_name")
        if not description:
            errors.append(f"entity `{entity_id or index}` requires description")
        if entity_type not in ENTITY_TYPES:
            errors.append(
                f"supply_chain rejects entity `{entity_id or index}` type `{entity_type or 'missing'}`"
            )
        prior = entity_types.get(entity_id)
        if prior is not None and prior != entity_type:
            errors.append(f"conflicting types for entity `{entity_id}`: `{prior}` and `{entity_type}`")
        if entity_id:
            entity_types[entity_id] = entity_type
        _validate_evidence(errors, f"entity `{entity_id or index}`", entity.get("source_id"), chunk_ids)
        normalized_entities.append(
            {
                **entity,
                "entity_name": entity_id,
                "entity_type": entity_type,
                "description": description,
                "file_path": str(entity.get("file_path", file_path)).strip() or file_path,
            }
        )

    normalized_relationships: list[dict[str, Any]] = []
    for index, relationship in enumerate(relationships):
        if not isinstance(relationship, dict):
            errors.append(f"relationship at index {index} must be an object")
            continue
        src_id = str(relationship.get("src_id") or relationship.get("source_entity") or "").strip()
        tgt_id = str(relationship.get("tgt_id") or relationship.get("target_entity") or "").strip()
        rel_type = relationship_type(relationship)
        description = str(relationship.get("description", "")).strip()
        if not description:
            errors.append(f"relationship `{src_id or index}->{tgt_id or index}` requires description")
        try:
            float(relationship.get("weight", 1.0))
        except (TypeError, ValueError):
            errors.append(f"relationship `{src_id or index}->{tgt_id or index}` weight must be numeric")
        expected = RELATIONSHIP_RULES.get(rel_type)
        if expected is None:
            errors.append(
                f"supply_chain rejects relationship `{src_id or index}->{tgt_id or index}` "
                f"type `{rel_type or 'missing'}`"
            )
        elif (entity_types.get(src_id), entity_types.get(tgt_id)) != expected:
            errors.append(
                f"supply_chain requires `{rel_type}` to connect {expected[0]} -> {expected[1]}, "
                f"got {entity_types.get(src_id, 'missing')} -> {entity_types.get(tgt_id, 'missing')}`"
            )
        _validate_evidence(
            errors,
            f"relationship `{src_id or index}->{tgt_id or index}`",
            relationship.get("source_id"),
            chunk_ids,
        )
        normalized_relationships.append(
            {
                **relationship,
                "src_id": src_id,
                "tgt_id": tgt_id,
                "relationship_type": rel_type,
                "description": description,
                "file_path": str(relationship.get("file_path", file_path)).strip() or file_path,
            }
        )

    if errors:
        return None, errors
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        PreparedPayload(
            document_id=document_id,
            file_path=file_path,
            snapshot_effective_date=snapshot_date,
            chunks=tuple(normalized_chunks),
            entities=tuple(normalized_entities),
            relationships=tuple(normalized_relationships),
            fingerprint=sha256(canonical.encode()).hexdigest(),
        ),
        [],
    )


def _required_text(payload: dict[str, Any], field: str, errors: list[str]) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        errors.append(f"{field} is required")
    return value


def _list_field(payload: dict[str, Any], field: str, errors: list[str]) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    return value


def _validate_evidence(
    errors: list[str], record_name: str, value: Any, resolvable_chunk_ids: set[str]
) -> None:
    references = source_ids(value)
    if not references:
        errors.append(f"supply_chain requires evidence for {record_name}")
        return
    unresolved = [item for item in references if item not in resolvable_chunk_ids]
    if unresolved:
        errors.append(
            f"supply_chain rejects {record_name} with unresolvable source_id(s): "
            + ", ".join(unresolved)
        )
