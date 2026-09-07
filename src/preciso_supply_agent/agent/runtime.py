"""Execution and checkpoint facade for the Supply Center graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from preciso_supply_agent.agent.graph import AgentDependencies, create_supply_graph
from preciso_supply_agent.agent.state import SupplyAgentState


@dataclass(frozen=True)
class RunSnapshot:
    thread_id: str
    state: dict[str, Any]
    status: str
    interrupts: list[dict[str, Any]]


class SupplyAgentRuntime:
    """Runs/resumes graph threads and reads only checkpointed workflow state."""

    def __init__(self, dependencies: AgentDependencies, checkpointer: BaseCheckpointSaver):
        self.graph = create_supply_graph(dependencies, checkpointer)

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    async def run(self, thread_id: str, state: SupplyAgentState) -> RunSnapshot:
        async for _update in self.graph.astream(
            state,
            config=self._config(thread_id),
            stream_mode="updates",
            version="v1",
        ):
            # Node-produced execution events are checkpointed in state. The
            # stream is consumed here so the request does not return early.
            pass
        return await self.snapshot(thread_id)

    async def resume(self, thread_id: str, *, approved: bool) -> RunSnapshot:
        async for _update in self.graph.astream(
            Command(resume={"approved": approved}),
            config=self._config(thread_id),
            stream_mode="updates",
            version="v1",
        ):
            pass
        return await self.snapshot(thread_id)

    async def snapshot(self, thread_id: str) -> RunSnapshot:
        checkpoint = await self.graph.aget_state(self._config(thread_id))
        values = dict(checkpoint.values or {})
        interrupts: list[dict[str, Any]] = []
        for task in checkpoint.tasks:
            for item in getattr(task, "interrupts", ()):
                value = getattr(item, "value", item)
                if isinstance(value, dict):
                    interrupts.append(value)
        if interrupts or values.get("awaiting_approval"):
            status = "awaiting_approval"
        elif values.get("preciso_status", {}).get("overall") == "error":
            status = "failed"
        else:
            status = "completed"
        return RunSnapshot(thread_id=thread_id, state=values, status=status, interrupts=interrupts)
