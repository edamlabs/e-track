"""tests/integration/etrack/logic/viewer: a real deep-agent run watched end to end through the viewer on a real port.

The agent runs tracked into the live sink; the viewer, served by granian on a free port, is read the way the canvas
reads it — the laid-out topology with its labels, the thread list, and the thread's frames over Server-Sent Events,
replayed and then followed while a second run goes on. No sandbox: every collaborator here runs in the process."""

import json
from typing import TYPE_CHECKING, Any, Final

import anyio
import httpx
import pytest
from deepagents import create_deep_agent
from langchain_core.tools import tool

from etrack.infra.config.providers.adapters.server.granian import GranianSettings
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.logic.viewer import Viewer
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter
from support.model import call, script
from support.port import free_port

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration

LABELS: Final[dict[str, str]] = {"PatchToolCallsMiddleware.before_agent": "Patch tool calls"}
WAIT: Final[float] = 20.0


@tool
def onto_query(query: str) -> str:
    """Run a SPARQL query."""
    return "seg:Poliza"


def deep_agent() -> Any:
    return create_deep_agent(
        model=script(
            call("task", "c1", subagent_type="ontologo", description="resolve Poliza"),
            call("onto_query", "c2", query="SELECT *"),
            "Poliza es seg:Poliza",
            "listo",
        ),
        subagents=[
            {"name": "ontologo", "description": "ontología", "system_prompt": "ontólogo", "tools": [onto_query]}
        ],
    )


async def frames(lines: AsyncIterator[str], count: int) -> list[dict[str, Any]]:
    """The next `count` SSE frames of a stream, each as its id and decoded event."""
    found: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    with anyio.fail_after(WAIT):
        ### SSE is line-framed: a blank line closes a message.
        async for line in lines:
            match line.partition(": ") if line else ("", "", ""):
                case ("", _, _):
                    found += [current] if current else []
                    current = {}
                case ("data", _, data):
                    current["event"] = json.loads(data)
                case (key, _, value):
                    current[key] = value
            if len(found) == count:
                break
    return found


async def test_viewer_deep_agent_end_to_end() -> None:
    async with LiveAdapter() as live:
        bus = AnyioAdapter()
        bus.subscribe(live)
        async with bus:
            tracker = Tracker(EventChannel(bus, forward=None), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
            with tracker.track("e2e", {}) as first:
                await deep_agent().ainvoke({"messages": [("user", "¿qué es una póliza?")]}, first.config)
            kept = live.offset("e2e")
            viewer = Viewer(watch=live, topology=LanggraphTopologyAdapter().read(deep_agent()), labels=LABELS)
            settings = GranianSettings(port=free_port())
            async with (
                GranianAdapter(viewer.app, settings) as server,
                httpx.AsyncClient(base_url=server.url, timeout=WAIT) as client,
            ):
                topology = (await client.get("/api/topology")).json()
                labels = {node["name"]: node.get("label", "") for node in topology["nodes"]}
                assert labels["PatchToolCallsMiddleware.before_agent"] == "Patch tool calls"
                assert topology["ranks"] > 1
                threads = (await client.get("/api/threads")).json()
                assert [(thread["thread"], thread["offset"], thread["runs"]) for thread in threads] == [
                    ("e2e", kept, [first.scope.run_id])
                ]
                assert (await client.get("/")).status_code == 200
                async with client.stream("GET", "/api/threads/e2e/events") as reply:
                    lines = reply.aiter_lines()
                    replayed = await frames(lines, kept)
                    with tracker.track("e2e", {}) as second:
                        await deep_agent().ainvoke({"messages": [("user", "¿y una prima?")]}, second.config)
                    followed = await frames(lines, live.offset("e2e") - kept)
    ### the replay and the follow are one contiguous stream: every offset once, in order, across both runs.
    offsets = [int(frame["id"]) for frame in replayed + followed]
    assert offsets == list(range(len(offsets)))
    runs = {frame["event"]["run_id"] for frame in replayed + followed}
    assert runs == {first.scope.run_id, second.scope.run_id}
    kinds = {frame["event"]["kind"] for frame in replayed}
    assert {"run", "node", "llm", "subagent", "mcp"} <= kinds
