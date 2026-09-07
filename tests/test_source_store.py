from pathlib import Path

import pytest

from preciso_supply_agent.documents.readers import read_source
from preciso_supply_agent.documents.store import SourceStore


def test_source_store_persists_and_resolves_by_id(tmp_path: Path) -> None:
    store = SourceStore(tmp_path / "uploads")
    source = store.create(name="source.md", content="recorded fact")

    loaded = store.get(source["source_id"])

    assert "content" not in loaded
    assert read_source(loaded)["content"] == "recorded fact"
    with pytest.raises(KeyError):
        store.get("source:../outside")
