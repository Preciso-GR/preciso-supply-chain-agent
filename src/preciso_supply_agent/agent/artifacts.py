"""Per-document extraction artifact storage owned by Supply Center."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ExtractionArtifactStore:
    def __init__(self, root: Path):
        self.root = root

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
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"artifact_name": artifact_name, "artifact_path": str(path)}
