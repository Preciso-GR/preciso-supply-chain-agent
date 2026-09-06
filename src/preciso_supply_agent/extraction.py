"""Claude-backed extraction boundary for SUPPLY CENTER.

The model proposes a payload. Preciso remains the authority that validates and
persists it after explicit human approval.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "fixtures" / "supply_chain" / "canonical_id_registry.json"


class ExtractionError(RuntimeError):
    """Raised when the configured extraction provider cannot produce a payload."""


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_json(raw_output: str) -> dict[str, Any]:
    candidate = raw_output.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Claude returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ExtractionError("Claude extraction output must be a JSON object")
    return payload


@dataclass(frozen=True)
class ClaudeExtractor:
    """Minimal Anthropic Messages API client with no browser-visible credentials."""

    api_key: str | None = None
    model: str = "claude-sonnet-5"
    endpoint: str = "https://api.anthropic.com/v1/messages"

    @classmethod
    def from_environment(cls) -> "ClaudeExtractor":
        return cls(
            api_key=os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"),
            model=os.getenv("SUPPLY_CENTER_CLAUDE_MODEL", "claude-sonnet-5").strip()
            or "claude-sonnet-5",
            endpoint=os.getenv(
                "SUPPLY_CENTER_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages"
            ).strip(),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model and self.endpoint)

    def status(self) -> dict[str, Any]:
        return {
            "provider": "anthropic",
            "configured": self.configured,
            "model": self.model if self.configured else None,
        }

    async def extract(
        self,
        documents: list[dict[str, str]],
        *,
        snapshot_effective_date: str,
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.configured:
            raise ExtractionError(
                "Claude extraction is not configured. Set ANTHROPIC_API_KEY (or "
                "CLAUDE_API_KEY) on the API process."
            )

        system = """You extract documented supply-chain facts into Preciso's strict JSON contract.
Return one JSON object and no prose. Use only the supplied documents and canonical-ID registry.

Allowed entity types: COMPANY, FACILITY, COMPONENT, PRODUCT.
Allowed directed edges: COMPANY OPERATES FACILITY; FACILITY MANUFACTURES COMPONENT;
COMPONENT USED_IN PRODUCT. Put the relationship type first in `keywords`.

The object must contain: document_id, file_path, snapshot_effective_date, chunks, entities,
relationships. Every entity and relationship must cite a source_id for a chunk in `chunks`.
Every chunk must contain chunk_id, content, chunk_order_index, and file_path. Every entity must
contain entity_name (canonical ID), entity_type, description, source_id, and file_path. Every
relationship must contain src_id, tgt_id, keywords, description, source_id, file_path, and weight.

Extract direct documented claims only. Do not infer missing dependencies, alternatives, capacity,
inventory, orders, delays, severity, forecasts, or business impact. Never resolve an ambiguous
name. Reuse a canonical ID only when the registry permits it or the document directly states it.
If a document does not support a relationship, omit that relationship rather than completing a path.
Preserve source wording in coherent evidence chunks. Use the supplied snapshot date in descriptions."""
        source_bundle = {
            "snapshot_effective_date": snapshot_effective_date,
            "canonical_id_registry": registry,
            "documents": documents,
        }
        request_body = {
            "model": self.model,
            "max_tokens": 12000,
            "system": system,
            "messages": [
                {
                    "role": "user",
                    "content": "Extract this source bundle. Do not use outside knowledge.\n"
                    + json.dumps(source_bundle, ensure_ascii=False),
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "x-api-key": str(self.api_key),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=request_body,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExtractionError(f"Claude extraction request failed: {exc}") from exc

        raw_output = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        payload = _extract_json(raw_output)
        return {
            "status": "success",
            "provider": "anthropic",
            "model": self.model,
            "raw_output": raw_output,
            "payload": payload,
            "usage": body.get("usage", {}),
            "notice": "Model output is untrusted until reviewed and accepted by Preciso validation.",
        }
