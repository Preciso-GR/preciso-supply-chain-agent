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

    assert "must be exactly one existing" in skill
    assert "Never use comma-separated IDs" in skill


@pytest.mark.asyncio
async def test_unconfigured_extractor_never_attempts_a_request() -> None:
    extractor = ClaudeExtractor(api_key=None)

    with pytest.raises(ExtractionError, match="not configured"):
        await extractor.extract([], snapshot_effective_date="2026-01-15", registry={})
