"""Standalone ingestion, readiness, and deterministic dependency traversal."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sqlite3
from typing import Any

from preciso_supply_agent.core.models import LIMITATIONS, WORKSPACE
from preciso_supply_agent.core.storage import (
    DocumentConflict,
    EntityTypeConflict,
    SnapshotConflict,
    SupplyChainStore,
)
from preciso_supply_agent.core.validation import validate_payload


class SupplyChainEngine:
    def __init__(self, database_path: str | Path):
        self.store = SupplyChainStore(database_path)

    def ingest(self, payload: Any) -> dict[str, Any]:
        prepared, errors = validate_payload(payload)
        if errors or prepared is None:
            return self._validation_failure(errors)
        try:
            return self.store.ingest(prepared)
        except (SnapshotConflict, DocumentConflict, EntityTypeConflict) as exc:
            return self._validation_failure([str(exc)], document_id=prepared.document_id)
        except (sqlite3.Error, OSError) as exc:
            try:
                self.store.record_failure(prepared, str(exc))
            except (sqlite3.Error, OSError):
                # The original storage exception remains the useful failure. A
                # fully unavailable database cannot persist its own failure marker.
                pass
            return {
                "status": "error",
                "document_id": prepared.document_id,
                "message": "Storage failed; the document was not committed.",
                "errors": [str(exc)],
            }

    def status(self) -> dict[str, Any]:
        return self.store.status()

    def investigate_facility(self, facility_id: str, *, max_paths: int = 100) -> dict[str, Any]:
        facility_id = str(facility_id or "").strip()
        if max_paths <= 0:
            return self._base_response(
                "invalid_request",
                facility_id,
                message="max_paths must be greater than zero.",
            )

        entity = self.store.entity(facility_id) if facility_id else None
        if entity is None:
            return self._base_response(
                "unknown_facility",
                facility_id,
                message=(
                    "The requested facility is not documented in this dataset. "
                    "Provide a canonical facility ID; no alias was guessed."
                ),
            )
        if entity["entity_type"] != "FACILITY":
            response = self._base_response(
                "wrong_entity_type",
                facility_id,
                message="The requested entity is documented but is not a FACILITY.",
            )
            response["resolved_entity"] = entity
            return response

        readiness = self.store.status()
        if not readiness["readiness"]:
            response = self._base_response(
                "inconsistent_storage",
                facility_id,
                message="Supply-chain ingestion is incomplete; repair or reingest before querying.",
            )
            response["resolved_facility"] = entity
            response["incomplete_documents"] = readiness["ingestion_state"]["incomplete_documents"]
            return response

        raw_paths = self.store.candidate_paths(facility_id)
        if not raw_paths:
            response = self._base_response(
                "no_documented_paths",
                facility_id,
                message=(
                    "No documented component-to-product paths start at this facility. "
                    "This does not prove no real-world exposure."
                ),
            )
            response["resolved_facility"] = entity
            return response

        # Validate every candidate before applying the presentation limit. A broken
        # hidden path must not be disguised as a complete or merely truncated answer.
        rendered: list[dict[str, Any]] = []
        missing_source_ids: list[str] = []
        for manufactures, used_in in raw_paths:
            first, missing_first = self.store.render_edge(manufactures)
            second, missing_second = self.store.render_edge(used_in)
            missing_source_ids.extend(missing_first)
            missing_source_ids.extend(missing_second)
            if first is not None and second is not None:
                rendered.append(
                    {
                        "nodes": [facility_id, manufactures["tgt_id"], used_in["tgt_id"]],
                        "edges": [first, second],
                    }
                )
        if missing_source_ids:
            response = self._base_response(
                "inconsistent_evidence",
                facility_id,
                message=(
                    "Directed relationship evidence is missing or inconsistent; "
                    "no partial paths were returned."
                ),
            )
            response["resolved_facility"] = entity
            response["missing_source_ids"] = sorted(set(missing_source_ids))
            return response

        selected = rendered[:max_paths]
        products: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for path in selected:
            products[path["nodes"][-1]].append(path)
        response = self._base_response(
            "success",
            facility_id,
            message="Documented dependency paths found.",
            products=[
                {
                    "product_id": product_id,
                    "conclusion": "Potentially exposed through documented dependencies.",
                    "paths": paths,
                }
                for product_id, paths in sorted(products.items())
            ],
            is_truncated=len(rendered) > len(selected),
            max_paths=max_paths,
        )
        response["resolved_facility"] = entity
        return response

    def _base_response(
        self,
        status: str,
        facility_id: str,
        *,
        message: str,
        products: list[dict[str, Any]] | None = None,
        is_truncated: bool = False,
        max_paths: int = 100,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "workspace": WORKSPACE,
            "snapshot": self.store.status()["snapshot"],
            "scenario": {
                "type": "facility_unavailable",
                "facility_id": facility_id,
                "hypothetical": True,
            },
            "message": message,
            "potentially_exposed_products": products or [],
            "completeness": {"is_truncated": is_truncated, "max_paths": max_paths},
            "limitations": list(LIMITATIONS),
        }

    @staticmethod
    def _validation_failure(
        errors: list[str], document_id: str | None = None
    ) -> dict[str, Any]:
        return {
            "status": "validation_failed",
            "document_id": document_id,
            "message": "Supply-chain profile validation failed before writes.",
            "chunks_ingested": 0,
            "entities_merged": 0,
            "relationships_merged": 0,
            "ingestion_counts": {
                "chunks": {"added": 0, "skipped_duplicate": 0},
                "entities": {"added": 0, "skipped_duplicate": 0},
                "relationships": {"added": 0, "skipped_duplicate": 0},
            },
            "errors": errors,
            "warnings": [],
        }
