"""Deterministic analyst-intent and canonical facility resolution."""

from __future__ import annotations

from typing import Any

FACILITY_TERMS = ("unavailable", "exposed", "affected", "impact", "disruption", "facility")


def resolve_chat_intent(message: str, registry: dict[str, Any]) -> dict[str, Any]:
    normalized = " ".join(message.casefold().split())
    if not normalized:
        return {"status": "invalid_request", "message": "Enter an investigation question."}

    for ambiguous in registry.get("ambiguous_aliases", []):
        alias = str(ambiguous.get("alias", "")).strip()
        if alias and alias.casefold() in normalized:
            return {
                "status": "ambiguous_identity",
                "message": f"{alias} is explicitly unresolved and was not mapped to a facility.",
                "alias": alias,
            }

    matches: list[dict[str, str]] = []
    for entity in registry.get("entities", []):
        if entity.get("entity_type") != "FACILITY":
            continue
        names = [entity.get("canonical_id", ""), entity.get("display_name", "")]
        names.extend(alias.get("alias", "") for alias in entity.get("documented_aliases", []))
        if any(str(name).strip().casefold() in normalized for name in names if str(name).strip()):
            matches.append(entity)

    unique = {item["canonical_id"]: item for item in matches}
    if len(unique) > 1:
        return {
            "status": "ambiguous_request",
            "message": "The question names more than one facility. Ask about one facility at a time.",
            "facility_ids": sorted(unique),
        }
    if len(unique) == 1:
        facility = next(iter(unique.values()))
        return {
            "status": "resolved",
            "intent": "facility_unavailable",
            "facility_id": facility["canonical_id"],
            "facility_name": facility.get("display_name", facility["canonical_id"]),
        }
    if any(term in normalized for term in FACILITY_TERMS):
        return {
            "status": "facility_required",
            "message": "Name a documented facility or enter its canonical ID.",
        }
    return {
        "status": "unsupported_intent",
        "message": (
            "This prototype currently supports facility-unavailable dependency investigations. "
            "It does not forecast delay, inventory, severity, or business impact."
        ),
    }
