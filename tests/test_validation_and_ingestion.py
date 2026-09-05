from __future__ import annotations

from copy import deepcopy


def test_curated_fixture_ingests_atomically(engine, payload):
    result = engine.ingest(payload)

    assert result["status"] == "success"
    assert result["entities_merged"] == 11
    assert result["relationships_merged"] == 10
    assert engine.status()["readiness"] is True


def test_invalid_entity_type_is_rejected_before_writes(engine, payload):
    invalid = deepcopy(payload)
    invalid["entities"][0]["entity_type"] = "SUPPLIER"

    result = engine.ingest(invalid)

    assert result["status"] == "validation_failed"
    assert engine.status()["counts"]["entities"] == 0
    assert engine.status()["documents"] == []


def test_invalid_edge_direction_is_rejected_before_writes(engine, payload):
    invalid = deepcopy(payload)
    invalid["relationships"][3]["src_id"], invalid["relationships"][3]["tgt_id"] = (
        invalid["relationships"][3]["tgt_id"],
        invalid["relationships"][3]["src_id"],
    )

    result = engine.ingest(invalid)

    assert result["status"] == "validation_failed"
    assert any("FACILITY -> COMPONENT" in error for error in result["errors"])
    assert engine.status()["counts"]["relationships"] == 0


def test_unresolved_and_missing_evidence_are_rejected_before_writes(engine, payload):
    invalid = deepcopy(payload)
    invalid["relationships"][0]["source_id"] = "does_not_exist"
    invalid["relationships"][1]["source_id"] = ""

    result = engine.ingest(invalid)

    assert result["status"] == "validation_failed"
    assert any("unresolvable source_id" in error for error in result["errors"])
    assert any("requires evidence" in error for error in result["errors"])
    assert engine.status()["counts"]["chunks"] == 0


def test_base_record_contract_is_not_weakened(engine, payload):
    invalid = deepcopy(payload)
    invalid["entities"][0]["description"] = ""
    invalid["relationships"][0]["description"] = ""
    invalid["relationships"][1]["weight"] = "not-a-number"

    result = engine.ingest(invalid)

    assert result["status"] == "validation_failed"
    assert any("entity `company:arkon-components` requires description" in error for error in result["errors"])
    assert any("requires description" in error for error in result["errors"])
    assert any("weight must be numeric" in error for error in result["errors"])
    assert engine.status()["documents"] == []


def test_intentionally_invalid_fixture_is_rejected(engine):
    from conftest import load_fixture

    result = engine.ingest(load_fixture("invalid/unsupported_dependency.json"))

    assert result["status"] == "validation_failed"
    assert any("COMPONENT -> PRODUCT" in error for error in result["errors"])


def test_identical_reingestion_is_idempotent(engine, payload):
    assert engine.ingest(payload)["status"] == "success"

    repeated = engine.ingest(payload)

    assert repeated["status"] == "success"
    assert repeated["ingestion_counts"]["relationships"] == {
        "added": 0,
        "skipped_duplicate": 10,
    }
    assert engine.status()["counts"]["relationship_evidence"] == 10


def test_changed_document_content_requires_new_identity(engine, payload):
    assert engine.ingest(payload)["status"] == "success"
    changed = deepcopy(payload)
    changed["chunks"][0]["content"] += " Changed."

    result = engine.ingest(changed)

    assert result["status"] == "validation_failed"
    assert any("different content" in error for error in result["errors"])
    assert engine.status()["readiness"] is True


def test_mixed_snapshot_dates_are_rejected(engine, payload):
    assert engine.ingest(payload)["status"] == "success"
    other = deepcopy(payload)
    other["document_id"] = "other-snapshot"
    other["snapshot_effective_date"] = "2026-02-01"

    result = engine.ingest(other)

    assert result["status"] == "validation_failed"
    assert any("cannot mix" in error for error in result["errors"])
    assert engine.status()["snapshot"]["effective_dates"] == ["2026-01-15"]


def test_status_reports_counts_snapshot_and_commit_state(engine, payload):
    empty = engine.status()
    assert empty["status"] == "not_ready"
    assert empty["readiness"] is False

    engine.ingest(payload)
    status = engine.status()

    assert status["status"] == "ready"
    assert status["snapshot"] == {
        "effective_dates": ["2026-01-15"],
        "document_ids": ["synthetic_supply_chain_snapshot_2026_01_15"],
    }
    assert status["counts"] == {
        "chunks": 6,
        "entities": 11,
        "relationships": 10,
        "relationship_evidence": 10,
    }
