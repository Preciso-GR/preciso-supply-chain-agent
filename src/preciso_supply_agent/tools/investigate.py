from __future__ import annotations

from typing import Any

from preciso_supply_agent.core.engine import SupplyChainEngine


def investigate_facility(
    engine: SupplyChainEngine, facility_id: str, *, max_paths: int = 100
) -> dict[str, Any]:
    """Find evidence-backed product exposure along authoritative directed paths."""
    return engine.investigate_facility(facility_id, max_paths=max_paths)

