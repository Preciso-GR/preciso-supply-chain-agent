from __future__ import annotations

from typing import Any

from preciso_supply_agent.core.engine import SupplyChainEngine


def get_supply_chain_status(engine: SupplyChainEngine) -> dict[str, Any]:
    return engine.status()

