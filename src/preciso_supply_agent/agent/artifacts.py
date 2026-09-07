"""Per-document extraction artifact storage owned by Supply Center."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

EditOperation = Literal[
    "replace_entity",
    "replace_relationship",
    "replace_chunk",
    "add_entity",
    "add_relationship",
    "add_chunk",
    "remove_entity",
    "remove_relationship",
    "remove_chunk",
]

_COLLECTION_FOR_OPERATION = {
    "replace_entity": "entities",
    "replace_relationship": "relationships",
    "replace_chunk": "chunks",
    "add_entity": "entities",
    "add_relationship": "relationships",
    "add_chunk": "chunks",
    "remove_entity": "entities",
    "remove_relationship": "relationships",
    "remove_chunk": "chunks",
}


@dataclass(frozen=True)
class ExtractionPatch:
    """A typed, structured edit proposed for one extraction artifact."""

    operation: EditOperation
    match: dict[str, Any] = field(default_factory=dict)
    replacement: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ExtractionPatch:
        """Parse the model-facing patch shape without accepting raw text edits."""

        operation = payload.get("operation")
        if operation not in _COLLECTION_FOR_OPERATION:
            raise ValueError(f"unsupported extraction edit operation: {operation!r}")
        raw_match = payload.get("match", payload.get("target", {}))
        if isinstance(raw_match, str):
            key = {
                "entity": "entity_name",
                "relationship": "relationship",
                "chunk": "chunk_id",
            }
            kind = operation.split("_", 1)[1]
            raw_match = {key[kind]: raw_match}
        if not isinstance(raw_match, Mapping):
            raise TypeError("extraction edit match must be an object")
        raw_replacement = payload.get("replacement", payload.get("value"))
        if raw_replacement is not None and not isinstance(raw_replacement, Mapping):
            raise TypeError("extraction edit replacement must be an object")
        return cls(
            operation=operation,
            match=dict(raw_match),
            replacement=dict(raw_replacement) if raw_replacement is not None else None,
        )


class ExtractionArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def _resolve_artifact_path(self, artifact_path: str | Path) -> Path:
        candidate = Path(artifact_path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError("artifact_path must be inside the extraction artifact store") from exc
        return resolved

    @staticmethod
    def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)

    def write(self, source_name: str, source_id: str, payload: dict[str, Any]) -> dict[str, str]:
        self.root.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(source_name).stem).strip("._-")
        stem = stem or "source"
        artifact_name = f"{stem}_extracted.json"
        path = self.root / artifact_name
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if f'"document_id": "document:{source_id}"' not in existing:
                artifact_name = f"{stem}_{source_id[:8]}_extracted.json"
                path = self.root / artifact_name
        self._write_json_atomically(path, payload)
        return {"artifact_name": artifact_name, "artifact_path": str(path)}

    def read_payload(self, artifact_path: str | Path) -> dict[str, Any]:
        """Read one artifact after a structured edit has been applied."""

        path = self._resolve_artifact_path(artifact_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("extraction artifact must contain a JSON object")
        return payload

    def edit_extraction(
        self,
        artifact_path: str | Path,
        patch: ExtractionPatch,
    ) -> dict[str, Any]:
        """Apply one uniquely targeted structured edit in place.

        Replacement edits merge only the supplied fields into the matched
        object. This preserves fields the patch did not request and prevents a
        repair from accidentally dropping source evidence or metadata.
        """

        try:
            path = self._resolve_artifact_path(artifact_path)
        except ValueError as exc:
            return {
                "status": "error",
                "reason": "artifact_path_invalid",
                "artifact_path": str(artifact_path),
                "message": str(exc),
            }
        if not path.is_file():
            return {
                "status": "error",
                "reason": "artifact_not_found",
                "artifact_path": str(path),
            }
        try:
            payload = self.read_payload(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return {
                "status": "error",
                "reason": "artifact_invalid",
                "artifact_path": str(path),
                "message": str(exc),
            }

        collection_name = _COLLECTION_FOR_OPERATION.get(patch.operation)
        if collection_name is None:
            return {
                "status": "error",
                "reason": "unsupported_operation",
                "artifact_path": str(path),
                "operation": patch.operation,
            }
        collection = payload.get(collection_name)
        if not isinstance(collection, list) or any(not isinstance(item, dict) for item in collection):
            return {
                "status": "error",
                "reason": "collection_invalid",
                "artifact_path": str(path),
                "operation": patch.operation,
                "collection": collection_name,
            }

        is_add = patch.operation.startswith("add_")
        is_remove = patch.operation.startswith("remove_")
        if is_add:
            if patch.replacement is None:
                return {
                    "status": "error",
                    "reason": "replacement_required",
                    "artifact_path": str(path),
                    "operation": patch.operation,
                }
            collection.append(dict(patch.replacement))
            self._write_json_atomically(path, payload)
            return {
                "status": "success",
                "artifact_path": str(path),
                "operation": patch.operation,
                "changed": 1,
                "target": dict(patch.match),
            }

        if not patch.match:
            return {
                "status": "error",
                "reason": "target_required",
                "artifact_path": str(path),
                "operation": patch.operation,
            }
        matches = [
            index
            for index, item in enumerate(collection)
            if all(item.get(key) == expected for key, expected in patch.match.items())
        ]
        if not matches:
            return {
                "status": "error",
                "reason": "target_not_found",
                "artifact_path": str(path),
                "operation": patch.operation,
                "target": dict(patch.match),
            }
        if len(matches) > 1:
            return {
                "status": "error",
                "reason": "multiple_targets",
                "artifact_path": str(path),
                "operation": patch.operation,
                "target": dict(patch.match),
                "matches": len(matches),
            }

        index = matches[0]
        if is_remove:
            collection.pop(index)
        else:
            if patch.replacement is None:
                return {
                    "status": "error",
                    "reason": "replacement_required",
                    "artifact_path": str(path),
                    "operation": patch.operation,
                    "target": dict(patch.match),
                }
            collection[index] = {**collection[index], **patch.replacement}
        self._write_json_atomically(path, payload)
        return {
            "status": "success",
            "artifact_path": str(path),
            "operation": patch.operation,
            "changed": 1,
            "target": dict(patch.match),
        }


def edit_extraction(
    artifact_path: str | Path,
    patch: ExtractionPatch,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Application-side tool entry point for one structured artifact edit."""

    path = Path(artifact_path)
    root = artifact_root or (path.parent if path.is_absolute() else Path.cwd())
    return ExtractionArtifactStore(root).edit_extraction(artifact_path, patch)
