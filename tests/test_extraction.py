from __future__ import annotations

import pytest

from preciso_supply_agent.extraction import (
    ClaudeExtractor,
    ExtractionError,
    _extract_json,
    load_extraction_skill,
)


def test_json_extraction_preserves_model_payload() -> None:
    raw = '```json\n{"document_id":"attempt-1","relationships":[]}\n```'

    assert _extract_json(raw) == {"document_id": "attempt-1", "relationships": []}


def test_json_extraction_rejects_non_json_without_repairing_it() -> None:
    with pytest.raises(ExtractionError, match="invalid JSON"):
        _extract_json("Here is the extraction: {}")


def test_supply_center_skill_requires_single_exact_evidence_chunk() -> None:
    skill = load_extraction_skill()

    assert "exactly one real chunk" in skill
    assert "Do not infer unsupported dependency" in skill


@pytest.mark.asyncio
async def test_unconfigured_extractor_never_attempts_a_request() -> None:
    extractor = ClaudeExtractor(api_key=None)

    with pytest.raises(ExtractionError, match="not configured"):
        await extractor.extract([], snapshot_effective_date="2026-01-15", registry={})


@pytest.mark.asyncio
async def test_repair_requests_a_minimal_patch_with_exact_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    extractor = ClaudeExtractor(api_key="test-key", model="test-model")
    captured: dict[str, str] = {}

    async def fake_request(_: ClaudeExtractor, **kwargs: object) -> tuple[dict[str, object], str]:
        captured.update({key: str(value) for key, value in kwargs.items()})
        return {"usage": {}}, '{"operation":"replace_relationship","match":{},"replacement":{}}'

    monkeypatch.setattr(ClaudeExtractor, "_request", fake_request)
    result = await extractor.repair_document(
        {"name": "zoox.md", "content": "documented source", "source_id": "zoox"},
        {"entities": [], "relationships": [], "chunks": []},
        ["MANUFACTURES must connect FACILITY -> COMPONENT"],
        snapshot_effective_date="2026-09-07",
        registry={"entities": []},
    )

    assert result["patch"]["operation"] == "replace_relationship"
    assert "MANUFACTURES must connect FACILITY -> COMPONENT" in captured["content"]
    assert "Preserve all valid extraction content" in captured["content"]
    assert "Do not regenerate the full extraction JSON" in captured["content"]
