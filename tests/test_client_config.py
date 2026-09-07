from pathlib import Path

from preciso_supply_agent.client import PrecisoMCPConfig


def test_default_mcp_config_uses_bundled_engine(monkeypatch, tmp_path: Path) -> None:
    engine = tmp_path / "engine" / "preciso-graphrag"
    launcher = engine / "scripts" / "mcp_launcher.sh"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("SUPPLY_CENTER_ROOT", str(tmp_path))
    monkeypatch.delenv("PRECISO_MCP_CWD", raising=False)
    monkeypatch.delenv("PRECISO_MCP_COMMAND", raising=False)
    monkeypatch.delenv("PRECISO_MCP_ARGS", raising=False)
    monkeypatch.delenv("GRAPHRAG_MCP_WORKDIR", raising=False)

    config = PrecisoMCPConfig.from_environment()

    assert config.cwd == engine
    assert config.command == str(launcher)
    assert config.args == ()
    assert config.env is not None
    assert config.env["GRAPHRAG_MCP_WORKDIR"] == str(tmp_path / "data" / "preciso")
