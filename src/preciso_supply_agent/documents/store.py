"""Application-owned, path-safe storage for uploaded source documents."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from preciso_supply_agent.documents.readers import SUPPORTED_EXTENSIONS


class SourceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.index_path = self.root / "sources.json"

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.index_path)

    def create(self, *, name: str, content: str) -> dict[str, Any]:
        extension = Path(name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported source format: {extension or name}")
        self.root.mkdir(parents=True, exist_ok=True)
        source_id = f"source:{uuid.uuid4().hex}"
        stored_name = f"{source_id.removeprefix('source:')}{extension}"
        path = (self.root / stored_name).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid source path")
        path.write_text(content, encoding="utf-8")
        record = {
            "source_id": source_id,
            "name": name,
            "extension": extension,
            "storage_path": str(path),
            "size": len(content.encode("utf-8")),
            "status": "uploaded",
        }
        records = self._load()
        records[source_id] = record
        self._save(records)
        return record

    def get(self, source_id: str) -> dict[str, Any]:
        record = self._load().get(source_id)
        if not isinstance(record, dict):
            raise KeyError(source_id)
        path = Path(str(record.get("storage_path", ""))).resolve()
        if path.parent != self.root or not path.is_file():
            raise ValueError("Stored source is unavailable")
        return dict(record)
