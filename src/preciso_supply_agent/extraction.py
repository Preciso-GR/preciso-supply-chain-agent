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
EXTRACTION_SKILL_PATH = REPOSITORY_ROOT / "skills" / "preciso-supply-center-extraction" / "SKILL.md"
REGISTRY_PATH = REPOSITORY_ROOT / "fixtures" / "supply_chain" / "canonical_id_registry.json"
AGENT_ROOT = Path(__file__).resolve().parent / "agent"
SYSTEM_PROMPT_PATH = AGENT_ROOT / "system_prompt.md"
EXTRACTION_PROMPT_PATH = AGENT_ROOT / "prompts" / "extraction.md"
REPAIR_PROMPT_PATH = AGENT_ROOT / "prompts" / "repair.md"
GROUNDED_ANSWER_PROMPT_PATH = AGENT_ROOT / "prompts" / "grounded_answer.md"


class ExtractionError(RuntimeError):
    """Raised when the configured extraction provider cannot produce a payload."""


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_extraction_skill(path: Path = EXTRACTION_SKILL_PATH) -> str:
    """Load the repo-local extraction contract used in the Claude system prompt."""
    return path.read_text(encoding="utf-8")


def load_system_prompt(path: Path = SYSTEM_PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def load_agent_prompt(name: str) -> str:
    paths = {
        "extraction": EXTRACTION_PROMPT_PATH,
        "repair": REPAIR_PROMPT_PATH,
        "grounded_answer": GROUNDED_ANSWER_PROMPT_PATH,
    }
    try:
        return paths[name].read_text(encoding="utf-8")
    except KeyError as exc:  # pragma: no cover - developer error
        raise ValueError(f"Unknown Supply Center prompt: {name}") from exc


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

    async def _request(
        self,
        *,
        system: str,
        content: str,
        max_tokens: int,
        timeout: float,
        error_prefix: str,
    ) -> tuple[dict[str, Any], str]:
        if not self.configured:
            raise ExtractionError(
                "Claude extraction is not configured. Set ANTHROPIC_API_KEY (or "
                "CLAUDE_API_KEY) on the API process."
            )
        request_body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
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
            raise ExtractionError(f"{error_prefix}: {exc}") from exc

        raw_output = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return body, raw_output

    @staticmethod
    def _normalize_document_payload(
        payload: dict[str, Any], document: dict[str, str], snapshot_effective_date: str
    ) -> dict[str, Any]:
        """Keep the model output document-scoped without inventing graph facts."""

        source_id = document.get("source_id", "source")
        normalized = dict(payload)
        normalized["document_id"] = f"document:{source_id}"
        normalized["file_path"] = document["name"]
        normalized["snapshot_effective_date"] = snapshot_effective_date
        for chunk in normalized.get("chunks", []):
            if isinstance(chunk, dict):
                chunk["file_path"] = document["name"]
        for item in [*normalized.get("entities", []), *normalized.get("relationships", [])]:
            if isinstance(item, dict):
                item["file_path"] = document["name"]
        return normalized

    async def extract_document(
        self,
        document: dict[str, str],
        *,
        snapshot_effective_date: str,
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract one source; multiple documents are never sent in one request."""

        source = {
            "snapshot_effective_date": snapshot_effective_date,
            "canonical_id_registry": registry,
            "document": document,
        }
        body, raw_output = await self._request(
            system=(load_system_prompt() + "\n\n" + load_extraction_skill()),
            content=load_agent_prompt("extraction")
            + "\n\nSource document:\n"
            + json.dumps(source, ensure_ascii=False),
            max_tokens=12000,
            timeout=180.0,
            error_prefix="Claude extraction request failed",
        )
        payload = self._normalize_document_payload(
            _extract_json(raw_output), document, snapshot_effective_date
        )
        return {
            "status": "success",
            "provider": "anthropic",
            "model": self.model,
            "raw_output": raw_output,
            "payload": payload,
            "usage": body.get("usage", {}),
            "notice": "Model output is untrusted until reviewed and accepted by Preciso validation.",
        }

    async def extract(
        self,
        documents: list[dict[str, str]],
        *,
        snapshot_effective_date: str,
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        """Compatibility adapter that still invokes one request per document."""

        if not self.configured:
            raise ExtractionError(
                "Claude extraction is not configured. Set ANTHROPIC_API_KEY (or "
                "CLAUDE_API_KEY) on the API process."
            )

        results = [
            await self.extract_document(
                document,
                snapshot_effective_date=snapshot_effective_date,
                registry=registry,
            )
            for document in documents
        ]
        if len(results) == 1:
            return results[0]
        return {
            "status": "success",
            "provider": "anthropic",
            "model": self.model,
            "results": results,
            "payloads": [result["payload"] for result in results],
            "notice": "Each source was extracted independently; payloads remain untrusted until validated.",
        }

    async def repair_document(
        self,
        document: dict[str, str],
        extraction: dict[str, Any],
        validation_errors: list[str],
        *,
        snapshot_effective_date: str,
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        source = {
            "snapshot_effective_date": snapshot_effective_date,
            "canonical_id_registry": registry,
            "document": document,
            "extraction": extraction,
            "validation_errors": validation_errors,
        }
        body, raw_output = await self._request(
            system=(load_system_prompt() + "\n\n" + load_extraction_skill()),
            content=load_agent_prompt("repair")
            + "\n\nRepair context:\n"
            + json.dumps(source, ensure_ascii=False),
            max_tokens=12000,
            timeout=180.0,
            error_prefix="Claude extraction repair request failed",
        )
        payload = self._normalize_document_payload(
            _extract_json(raw_output), document, snapshot_effective_date
        )
        return {
            "status": "success",
            "provider": "anthropic",
            "model": self.model,
            "raw_output": raw_output,
            "payload": payload,
            "usage": body.get("usage", {}),
        }

    async def answer(self, question: str, investigation: dict[str, Any]) -> dict[str, Any]:
        """Synthesize a user-facing answer from PRECISO evidence only."""
        if not self.configured:
            raise ExtractionError(
                "Claude grounded answers are not configured. Set ANTHROPIC_API_KEY "
                "on the API process."
            )
        system = load_system_prompt() + "\n\n" + load_agent_prompt("grounded_answer")
        request_body = {
            "model": self.model,
            "max_tokens": 1800,
            "system": system,
            "messages": [{
                "role": "user",
                "content": "Question:\n" + question + "\n\nPRECISO investigation result:\n"
                + json.dumps(investigation, ensure_ascii=False),
            }],
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
            raise ExtractionError(f"Claude grounded answer request failed: {exc}") from exc
        answer = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not answer:
            raise ExtractionError("Claude returned an empty grounded answer")
        return {"status": "success", "answer": answer, "model": self.model, "usage": body.get("usage", {})}
