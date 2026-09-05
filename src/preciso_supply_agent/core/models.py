"""Supply-chain vocabulary and normalized ingestion records."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


WORKSPACE = "supply_chain"
SOURCE_SEPARATOR = "<SEP>"
ENTITY_TYPES = frozenset({"COMPANY", "FACILITY", "COMPONENT", "PRODUCT"})
RELATIONSHIP_RULES = {
    "OPERATES": ("COMPANY", "FACILITY"),
    "MANUFACTURES": ("FACILITY", "COMPONENT"),
    "USED_IN": ("COMPONENT", "PRODUCT"),
}
LIMITATIONS = [
    "Results are potential exposure through documented dependencies only.",
    "Results do not establish delay, severity, inventory shortage, capacity, or business impact.",
]


def relationship_type(record: dict[str, Any]) -> str:
    keywords = record.get("keywords", "")
    if not isinstance(keywords, str):
        return ""
    return keywords.split(",", 1)[0].strip().upper()


def source_ids(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(SOURCE_SEPARATOR) if item.strip()]


def stable_id(prefix: str, *parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
    return f"{prefix}{sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class PreparedPayload:
    document_id: str
    file_path: str
    snapshot_effective_date: str
    chunks: tuple[dict[str, Any], ...]
    entities: tuple[dict[str, Any], ...]
    relationships: tuple[dict[str, Any], ...]
    fingerprint: str

