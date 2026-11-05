"""tests/integration/etrack/logic/viewer: a real deep-agent run watched end to end through the viewer on a real port.

The agent runs tracked into the live sink; the viewer, served by granian on a free port, is read the way the canvas
reads it — the laid-out topology with its labels, the thread list, and the thread's frames over Server-Sent Events,
replayed and then followed while a second run goes on. No sandbox: every collaborator here runs in the process."""

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from etrack.infra.config.providers import GranianConfig
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.logic.viewer import Viewer
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter
from support.port import free_port
from support.sse import sse

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.integration


async def test_viewer_deep_agent_end_to_end(
    deep_agent: Callable[[], Any], viewer_labels: dict[str, str], wait: float
) -> None:
    async with LiveAdapter() as live:
        bus = AnyioAdapter()
        bus.subscribe(live)
        async with bus:
            tracker = Tracker(EventChannel(bus, forward=None), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
            with tracker.track("e2e", {}) as first:
                await deep_agent().ainvoke({"messages": [("user", "¿qué es una póliza?")]}, first.config)
            kept = live.offset("e2e")
            viewer = Viewer(watch=live, topology=LanggraphTopologyAdapter().read(deep_agent()), labels=viewer_labels)
            settings = GranianConfig(port=free_port())
            async with (
                GranianAdapter(viewer.app, **settings) as server,
                httpx.AsyncClient(base_url=server.url, timeout=wait) as client,
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
                    replayed = await sse(lines, kept, wait)
                    with tracker.track("e2e", {}) as second:
                        await deep_agent().ainvoke({"messages": [("user", "¿y una prima?")]}, second.config)
                    followed = await sse(lines, live.offset("e2e") - kept, wait)
    ### the replay and the follow are one contiguous stream: every offset once, in order, across both runs.
    offsets = [int(frame["id"]) for frame in replayed + followed]
    assert offsets == list(range(len(offsets)))
    runs = {json.loads(frame["data"])["run_id"] for frame in replayed + followed}
    assert runs == {first.scope.run_id, second.scope.run_id}
    kinds = {json.loads(frame["data"])["kind"] for frame in replayed}
    assert {"run", "node", "llm", "subagent", "mcp"} <= kinds
