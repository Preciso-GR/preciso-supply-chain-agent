from __future__ import annotations

import json
from pathlib import Path

import pytest

from preciso_supply_agent import SupplyChainEngine


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "fixtures" / "supply_chain"


def load_fixture(relative_path: str = "expected_extraction.json") -> dict:
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


@pytest.fixture
def payload() -> dict:
    return load_fixture()


@pytest.fixture
def engine(tmp_path: Path) -> SupplyChainEngine:
    return SupplyChainEngine(tmp_path / "supply-chain.sqlite3")

