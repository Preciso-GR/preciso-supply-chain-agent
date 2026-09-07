from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from preciso_supply_agent.agent.artifacts import ExtractionArtifactStore, ExtractionPatch


def make_artifact(tmp_path: Path) -> tuple[ExtractionArtifactStore, Path, dict[str, Any]]:
    store = ExtractionArtifactStore(tmp_path / "extractions")
    payload = {
        "document_id": "document:source-one",
        "file_path": "source-one.md",
        "snapshot_effective_date": "2026-09-07",
        "chunks": [
            {"chunk_id": "source-one.md#chunk_001", "content": "Factory makes cells."},
            {"chunk_id": "source-one.md#chunk_002", "content": "Factory is in Kansas."},
        ],
        "entities": [
            {"entity_name": "company:panasonic-energy", "entity_type": "COMPANY", "description": "Panasonic"},
            {"entity_name": "facility:panasonic-energy:kansas", "entity_type": "FACILITY", "description": "Kansas"},
        ],
        "relationships": [
            {
                "src_id": "facility:panasonic-energy:kansas",
                "tgt_id": "component:panasonic-energy:cell",
                "keywords": "MANUFACTURES",
                "description": "Kansas makes the cell.",
            },
            {
                "src_id": "company:panasonic-energy",
                "tgt_id": "facility:panasonic-energy:kansas",
                "keywords": "OPERATES",
                "description": "Panasonic operates Kansas.",
            },
        ],
    }
    result = store.write("source-one.md", "source-one", payload)
    return store, Path(result["artifact_path"]), payload


def test_replace_entity_modifies_only_target_entity(tmp_path: Path) -> None:
    store, artifact_path, original = make_artifact(tmp_path)

    result = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="replace_entity",
            match={"entity_name": "facility:panasonic-energy:kansas"},
            replacement={"description": "Kansas cell facility."},
        ),
    )

    assert result["status"] == "success"
    updated = store.read_payload(artifact_path)
    assert updated["entities"][0] == original["entities"][0]
    assert updated["entities"][1]["description"] == "Kansas cell facility."
    assert updated["relationships"] == original["relationships"]
    assert updated["chunks"] == original["chunks"]


def test_replace_relationship_modifies_only_target_relationship(tmp_path: Path) -> None:
    store, artifact_path, original = make_artifact(tmp_path)

    result = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="replace_relationship",
            match={
                "src_id": "company:panasonic-energy",
                "tgt_id": "facility:panasonic-energy:kansas",
                "keywords": "OPERATES",
            },
            replacement={"description": "The company operates the Kansas facility."},
        ),
    )

    assert result["changed"] == 1
    updated = store.read_payload(artifact_path)
    assert updated["relationships"][0] == original["relationships"][0]
    assert updated["relationships"][1]["description"] == "The company operates the Kansas facility."
    assert updated["entities"] == original["entities"]
    assert updated["chunks"] == original["chunks"]


def test_replace_chunk_modifies_only_target_chunk(tmp_path: Path) -> None:
    store, artifact_path, original = make_artifact(tmp_path)

    result = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="replace_chunk",
            match={"chunk_id": "source-one.md#chunk_002"},
            replacement={"content": "The Kansas facility is documented."},
        ),
    )

    assert result["status"] == "success"
    updated = store.read_payload(artifact_path)
    assert updated["chunks"][0] == original["chunks"][0]
    assert updated["chunks"][1]["content"] == "The Kansas facility is documented."
    assert updated["entities"] == original["entities"]
    assert updated["relationships"] == original["relationships"]


def test_missing_and_ambiguous_targets_return_structured_errors(tmp_path: Path) -> None:
    store, artifact_path, _ = make_artifact(tmp_path)

    missing = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="replace_entity",
            match={"entity_name": "company:missing"},
            replacement={"description": "never written"},
        ),
    )
    assert missing["status"] == "error"
    assert missing["reason"] == "target_not_found"

    payload = store.read_payload(artifact_path)
    payload["entities"].append({"entity_name": "company:duplicate", "description": "one"})
    payload["entities"].append({"entity_name": "company:duplicate", "description": "two"})
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    ambiguous = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="replace_entity",
            match={"entity_name": "company:duplicate"},
            replacement={"description": "must not choose"},
        ),
    )
    assert ambiguous["status"] == "error"
    assert ambiguous["reason"] == "multiple_targets"
    assert [item["description"] for item in store.read_payload(artifact_path)["entities"][-2:]] == ["one", "two"]


def test_add_and_remove_are_explicit_structured_operations(tmp_path: Path) -> None:
    store, artifact_path, _ = make_artifact(tmp_path)

    added = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="add_entity",
            replacement={"entity_name": "component:panasonic-energy:cell", "entity_type": "COMPONENT"},
        ),
    )
    assert added["status"] == "success"
    removed = store.edit_extraction(
        artifact_path,
        ExtractionPatch(
            operation="remove_entity",
            match={"entity_name": "component:panasonic-energy:cell"},
        ),
    )
    assert removed["status"] == "success"
    assert all(item["entity_name"] != "component:panasonic-energy:cell" for item in store.read_payload(artifact_path)["entities"])
