"""Reproduce the curated positive and fail-closed demonstration cases."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile

from preciso_supply_agent import SupplyChainEngine


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "supply_chain" / "expected_extraction.json"
NORTHBRIDGE = "facility:arkon-components:northbridge"
DOCUMENT = "synthetic_supply_chain_snapshot_2026_01_15"


def compact(result: dict) -> dict:
    return {
        "status": result["status"],
        "products": [
            {
                "product_id": product["product_id"],
                "paths": [path["nodes"] for path in product["paths"]],
            }
            for product in result.get("potentially_exposed_products", [])
        ],
        "snapshot": result.get("snapshot"),
        "completeness": result.get("completeness"),
        "missing_source_ids": result.get("missing_source_ids", []),
    }


def main() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="preciso-supply-demo-") as temp_dir:
        engine = SupplyChainEngine(Path(temp_dir) / "complete.sqlite3")
        ingestion = engine.ingest(deepcopy(payload))
        if ingestion["status"] != "success":
            raise RuntimeError(ingestion)
        northbridge = engine.investigate_facility(NORTHBRIDGE)
        plant_7 = engine.investigate_facility("Plant 7")

        broken = SupplyChainEngine(Path(temp_dir) / "missing-evidence.sqlite3")
        if broken.ingest(deepcopy(payload))["status"] != "success":
            raise RuntimeError("could not prepare missing-evidence case")
        broken.store.delete_chunk(f"{DOCUMENT}::bom_001")
        missing_evidence = broken.investigate_facility(NORTHBRIDGE)

        print(
            json.dumps(
                {
                    "ingestion": ingestion["status"],
                    "northbridge": compact(northbridge),
                    "plant_7": compact(plant_7),
                    "missing_evidence": compact(missing_evidence),
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()

