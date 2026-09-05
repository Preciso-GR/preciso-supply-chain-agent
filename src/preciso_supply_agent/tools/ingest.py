from __future__ import annotations

from typing import Any

from preciso_supply_agent.core.engine import SupplyChainEngine


def ingest_supply_chain(engine: SupplyChainEngine, payload: Any) -> dict[str, Any]:
    """Validate and atomically commit one reviewed extraction payload."""
    return engine.ingest(payload)

