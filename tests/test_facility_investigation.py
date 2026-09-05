from __future__ import annotations

from copy import deepcopy


NORTHBRIDGE = "facility:arkon-components:northbridge"
DOCUMENT = "synthetic_supply_chain_snapshot_2026_01_15"


def product_ids(result):
    return {item["product_id"] for item in result["potentially_exposed_products"]}


def paths(result):
    return {
        tuple(path["nodes"])
        for product in result["potentially_exposed_products"]
        for path in product["paths"]
    }


def test_northbridge_returns_exact_directed_paths_and_evidence(engine, payload):
    assert engine.ingest(payload)["status"] == "success"

    result = engine.investigate_facility(NORTHBRIDGE)

    assert result["status"] == "success"
    assert product_ids(result) == {"product:aquapump:300", "product:aquapump:500"}
    assert paths(result) == {
        (NORTHBRIDGE, "component:arkon-components:control-unit-c17", "product:aquapump:300"),
        (NORTHBRIDGE, "component:arkon-components:control-unit-c17", "product:aquapump:500"),
    }
    assert "product:valvepro:10" not in product_ids(result)
    for product in result["potentially_exposed_products"]:
        for path in product["paths"]:
            assert [edge["relationship_type"] for edge in path["edges"]] == [
                "MANUFACTURES",
                "USED_IN",
            ]
            assert all(edge["evidence"][0]["chunk"]["content"] for edge in path["edges"])
    assert result["snapshot"]["effective_dates"] == ["2026-01-15"]
    assert result["completeness"] == {"is_truncated": False, "max_paths": 100}


def test_truncation_is_explicit_and_deterministic(engine, payload):
    engine.ingest(payload)

    result = engine.investigate_facility(NORTHBRIDGE, max_paths=1)

    assert result["status"] == "success"
    assert result["completeness"] == {"is_truncated": True, "max_paths": 1}
    assert product_ids(result) == {"product:aquapump:300"}


def test_multiple_paths_to_one_product_are_preserved(engine, payload):
    extra = deepcopy(payload)
    extra["document_id"] = "secondary"
    extra["chunks"] = [
        {"chunk_id": "secondary", "content": "Northbridge manufactures Sensor S-2, used in AquaPump 500."}
    ]
    extra["entities"] = [
        {"entity_name": NORTHBRIDGE, "entity_type": "FACILITY", "description": "Northbridge.", "source_id": "secondary"},
        {"entity_name": "component:arkon-components:sensor-s2", "entity_type": "COMPONENT", "description": "Sensor S-2.", "source_id": "secondary"},
        {"entity_name": "product:aquapump:500", "entity_type": "PRODUCT", "description": "AquaPump 500.", "source_id": "secondary"},
    ]
    extra["relationships"] = [
        {"src_id": NORTHBRIDGE, "tgt_id": "component:arkon-components:sensor-s2", "keywords": "MANUFACTURES", "description": "Northbridge manufactures Sensor S-2.", "source_id": "secondary"},
        {"src_id": "component:arkon-components:sensor-s2", "tgt_id": "product:aquapump:500", "keywords": "USED_IN", "description": "Sensor S-2 is used in AquaPump 500.", "source_id": "secondary"},
    ]
    engine.ingest(payload)
    assert engine.ingest(extra)["status"] == "success"

    result = engine.investigate_facility(NORTHBRIDGE)
    aquapump_500 = next(
        item for item in result["potentially_exposed_products"] if item["product_id"] == "product:aquapump:500"
    )

    assert len(aquapump_500["paths"]) == 2


def test_plant_7_remains_unknown_without_guessing(engine, payload):
    engine.ingest(payload)

    result = engine.investigate_facility("Plant 7")

    assert result["status"] == "unknown_facility"
    assert result["potentially_exposed_products"] == []
    assert "no alias was guessed" in result["message"]


def test_wrong_entity_type_is_distinct(engine, payload):
    engine.ingest(payload)

    result = engine.investigate_facility("product:aquapump:500")

    assert result["status"] == "wrong_entity_type"
    assert result["potentially_exposed_products"] == []


def test_missing_evidence_fails_closed(engine, payload):
    engine.ingest(payload)
    engine.store.delete_chunk(f"{DOCUMENT}::bom_001")

    result = engine.investigate_facility(NORTHBRIDGE)

    assert result["status"] == "inconsistent_evidence"
    assert result["potentially_exposed_products"] == []
    assert result["missing_source_ids"] == [f"{DOCUMENT}::bom_001"]


def test_incomplete_commit_fails_closed(engine, payload):
    engine.ingest(payload)
    engine.store.set_document_status(DOCUMENT, "pending")

    result = engine.investigate_facility(NORTHBRIDGE)

    assert result["status"] == "inconsistent_storage"
    assert result["potentially_exposed_products"] == []
    assert result["incomplete_documents"] == [DOCUMENT]


def test_reverse_direction_does_not_create_a_path(engine, payload):
    engine.ingest(payload)

    result = engine.investigate_facility("facility:redwood-materials:harbor")

    assert paths(result) == {
        (
            "facility:redwood-materials:harbor",
            "component:redwood-materials:valve-body-v2",
            "product:valvepro:10",
        )
    }
    assert "product:aquapump:500" not in product_ids(result)


def test_invalid_path_limit_is_not_an_empty_success(engine, payload):
    engine.ingest(payload)
    result = engine.investigate_facility(NORTHBRIDGE, max_paths=0)
    assert result["status"] == "invalid_request"


def test_facility_without_a_complete_dependency_path_is_distinct(engine):
    payload = {
        "document_id": "isolated-facility",
        "snapshot_effective_date": "2026-01-15",
        "chunks": [{"chunk_id": "one", "content": "Acme operates Quiet Plant."}],
        "entities": [
            {"entity_name": "company:acme", "entity_type": "COMPANY", "description": "Acme.", "source_id": "one"},
            {"entity_name": "facility:acme:quiet", "entity_type": "FACILITY", "description": "Quiet Plant.", "source_id": "one"},
        ],
        "relationships": [
            {"src_id": "company:acme", "tgt_id": "facility:acme:quiet", "keywords": "OPERATES", "description": "Acme operates Quiet Plant.", "source_id": "one"}
        ],
    }
    assert engine.ingest(payload)["status"] == "success"

    result = engine.investigate_facility("facility:acme:quiet")

    assert result["status"] == "no_documented_paths"
    assert result["potentially_exposed_products"] == []
