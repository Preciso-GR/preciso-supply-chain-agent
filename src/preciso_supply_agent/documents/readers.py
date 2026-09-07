"""Small, deterministic readers for the source formats supported in V1."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from preciso_supply_agent.agent.state import SourceRecord


SUPPORTED_EXTENSIONS = {".md", ".txt", ".csv", ".json"}


def read_source(source: SourceRecord) -> dict[str, Any]:
    """Read a source and preserve useful structure without extracting facts."""

    name = source["name"]
    extension = source.get("extension", "").lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported source format: {extension or name}")

    content = source["content"]
    result: dict[str, Any] = {
        "source_id": source["source_id"],
        "name": name,
        "file_path": name,
        "extension": extension,
        "content": content,
        "metadata": {"character_count": len(content)},
    }
    if extension == ".csv":
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        result["metadata"] = {
            **result["metadata"],
            "columns": reader.fieldnames or [],
            "row_count": len(rows),
        }
        result["rows"] = rows
    elif extension == ".json":
        result["structured"] = json.loads(content)
        if isinstance(result["structured"], dict):
            result["metadata"] = {
                **result["metadata"],
                "top_level_keys": list(result["structured"].keys()),
            }
    return result
