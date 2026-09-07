"""Execution, checkpoint, and live-event facade for the Supply Center graph."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from preciso_supply_agent.agent.graph import AgentDependencies, create_supply_graph
from preciso_supply_agent.agent.state import SupplyAgentState, execution_event


@dataclass(frozen=True)
class RunSnapshot:
    thread_id: str
    state: dict[str, Any]
    status: str
    interrupts: list[dict[str, Any]]


@dataclass
class _Run:
    run_id: str
    thread_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    closed: bool = False
    stream_complete: bool = False


class SupplyAgentRuntime:
    """Runs checkpointed graph threads and publishes their actual node events live."""

    def __init__(self, dependencies: AgentDependencies, checkpointer: BaseCheckpointSaver):
        self.graph = create_supply_graph(dependencies, checkpointer)
        self._runs: dict[str, _Run] = {}
        self._thread_runs: dict[str, str] = {}

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    async def start(self, thread_id: str, state: SupplyAgentState) -> str:
        run_id = str(state["run_id"])
        run = _Run(run_id=run_id, thread_id=thread_id)
        self._runs[run_id] = run
        self._thread_runs[thread_id] = run_id
        run.task = asyncio.create_task(self._drive(run, state), name=f"supply-agent:{run_id}")
        return run_id

    async def resume_live(self, thread_id: str, *, approved: bool) -> str:
        run = self._run_for_thread(thread_id)
        if run.task is not None and not run.task.done():
            raise RuntimeError("Run is already executing")
        if run.closed:
            raise RuntimeError("Run has already completed")
        run.stream_complete = False
        run.task = asyncio.create_task(
            self._drive(run, Command(resume={"approved": approved})),
            name=f"supply-agent:{run.run_id}",
        )
        return run.run_id

    async def run(self, thread_id: str, state: SupplyAgentState) -> RunSnapshot:
        """Synchronous facade retained for direct graph tests and embedding callers."""
        run_id = await self.start(thread_id, state)
        run = self.run_for_id(run_id)
        assert run.task is not None
        await run.task
        return await self.snapshot(thread_id)

    async def resume(self, thread_id: str, *, approved: bool) -> RunSnapshot:
        """Synchronous facade retained for direct graph tests and embedding callers."""
        run_id = await self.resume_live(thread_id, approved=approved)
        run = self.run_for_id(run_id)
        assert run.task is not None
        await run.task
        return await self.snapshot(thread_id)

    def _run_for_thread(self, thread_id: str) -> _Run:
        run_id = self._thread_runs.get(thread_id)
        if run_id is None or run_id not in self._runs:
            raise KeyError(thread_id)
        return self._runs[run_id]

    def run_for_id(self, run_id: str) -> _Run:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError(run_id) from exc

    async def _publish(self, run: _Run, event: dict[str, Any]) -> None:
        async with run.condition:
            run.events.append(event)
            run.condition.notify_all()

    async def _close(self, run: _Run) -> None:
        async with run.condition:
            run.closed = True
            run.stream_complete = True
            run.condition.notify_all()

    async def _finish_stream(self, run: _Run) -> None:
        async with run.condition:
            run.stream_complete = True
            run.condition.notify_all()

    @staticmethod
    def _events_from_update(update: Any) -> list[dict[str, Any]]:
        if not isinstance(update, dict):
            return []
        data = update.get("data", update)
        if not isinstance(data, dict):
            return []
        events: list[dict[str, Any]] = []
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get("events"), list):
                events.extend(event for event in value["events"] if isinstance(event, dict))
        return events

    async def _drive(self, run: _Run, input_state: SupplyAgentState | Command) -> None:
        try:
            async for update in self.graph.astream(
                input_state,
                config=self._config(run.thread_id),
                stream_mode="updates",
                version="v1",
            ):
                for event in self._events_from_update(update):
                    await self._publish(run, event)
            snapshot = await self.snapshot(run.thread_id)
            await self._publish(
                run,
                execution_event(
                    "run.status",
                    run_id=run.run_id,
                    data={"status": snapshot.status, "thread_id": run.thread_id},
                ),
            )
            if snapshot.status == "awaiting_approval":
                await self._finish_stream(run)
            else:
                await self._close(run)
        except Exception as exc:  # noqa: BLE001 - send a useful final SSE event
            await self._publish(
                run,
                execution_event(
                    "run.failed",
                    run_id=run.run_id,
                    data={"error": str(exc)},
                ),
            )
            await self._close(run)

    async def events(self, run_id: str, *, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        run = self.run_for_id(run_id)
        index = max(after, 0)
        while True:
            async with run.condition:
                while index >= len(run.events) and not run.stream_complete:
                    await run.condition.wait()
                if index < len(run.events):
                    event = run.events[index]
                    index += 1
                elif run.stream_complete:
                    return
                else:  # pragma: no cover
                    continue
            yield event

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
