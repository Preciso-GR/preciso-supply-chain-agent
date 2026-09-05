"""MCP transport for the Preciso Supply Chain application.

This package is an application client, not a second supply-chain engine.  The
Preciso GraphRAG repository remains authoritative for validation, persistence,
and dependency queries.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class PrecisoMCPError(RuntimeError):
    """Raised when the configured Preciso MCP backend cannot serve a request."""


@dataclass(frozen=True)
class PrecisoMCPConfig:
    """How the application starts the pinned Preciso MCP backend."""

    command: str = "python3"
    args: tuple[str, ...] = ("-m", "preciso_mcp.server")
    cwd: Path | None = None
    env: dict[str, str] | None = None

    @classmethod
    def from_environment(cls) -> "PrecisoMCPConfig":
        command = os.getenv("PRECISO_MCP_COMMAND", "python3").strip() or "python3"
        raw_args = os.getenv("PRECISO_MCP_ARGS", "-m preciso_mcp.server")
        args = tuple(shlex.split(raw_args))
        raw_cwd = os.getenv("PRECISO_MCP_CWD", "").strip()
        cwd = Path(raw_cwd).expanduser() if raw_cwd else None
        return cls(command=command, args=args, cwd=cwd)


class PrecisoMCPClient:
    """Small MCP client for the existing Preciso supply-chain contract."""

    def __init__(self, config: PrecisoMCPConfig | None = None):
        self.config = config or PrecisoMCPConfig.from_environment()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "PrecisoMCPClient":
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        parameters = StdioServerParameters(
            command=self.config.command,
            args=list(self.config.args),
            cwd=self.config.cwd,
            # The backend configuration (including its isolated working
            # directory and embedding provider) lives in environment variables.
            # MCP does not implicitly preserve them when `env` is omitted.
            env=self.config.env or dict(os.environ),
        )
        try:
            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(parameters)
            )
            self._session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
        except Exception as exc:
            await self._stack.aclose()
            self._stack = None
            raise PrecisoMCPError(
                "Could not connect to the configured Preciso MCP backend. "
                f"Check PRECISO_MCP_CWD and backend installation: {exc}"
            ) from exc
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(exc_type, exc, traceback)
        self._stack = None
        self._session = None

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise PrecisoMCPError("PrecisoMCPClient must be used inside an async context manager")
        try:
            result = await self._session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:
            raise PrecisoMCPError(f"Preciso MCP call `{tool_name}` failed: {exc}") from exc
        if getattr(result, "isError", False):
            raise PrecisoMCPError(f"Preciso MCP tool `{tool_name}` returned an error")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured
        for content in getattr(result, "content", []):
            text = getattr(content, "text", None)
            if not isinstance(text, str):
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise PrecisoMCPError(f"Preciso MCP tool `{tool_name}` returned no structured object")
