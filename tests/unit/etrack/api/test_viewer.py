"""tests/unit/etrack/api/viewer: the doors — topology, threads, a thread over SSE (replay, resume, follow), the canvas.

The SSE tests run against a real granian server on a free localhost port: an in-memory ASGI transport buffers the
whole response, and a stream never ends."""

from typing import TYPE_CHECKING, Any

import anyio
import httpx
import msgspec
import pytest
from litestar.testing import AsyncTestClient

from etrack.api.viewer import ViewerApi
from etrack.infra.config.providers.adapters.server.granian import GranianSettings
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from support.port import free_port
from unit.etrack.conftest import frame

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

TOPOLOGY = Topology(
    nodes=(TopologyNode(id="a", name="a", entry=True), TopologyNode(id="b", name="b", rank=1)),
    edges=(TopologyEdge(id="a>b:0", source="a", target="b"),),
    ranks=2,
    lanes=1,
)


async def filled(count: int, thread: str = "t1") -> LiveAdapter:
    live = LiveAdapter()
    _ = [await live.send(frame(seq, thread_id=thread)) for seq in range(count)]
    return live


async def messages(lines: AsyncIterator[str], count: int) -> list[dict[str, Any]]:
    """The next `count` SSE messages of a stream's lines, each as its fields."""
    found: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    with anyio.fail_after(2):
        ### SSE is line-framed: a blank line closes a message.
        async for line in lines:
            match line.partition(": ") if line else ("", "", ""):
                case ("", _, _):
                    found += [current] if current else []
                    current = {}
                case (key, _, value):
                    current[key] = value
            if len(found) == count:
                break
    return found


async def test_viewer_api_topology() -> None:
    async with AsyncTestClient(app=ViewerApi(TOPOLOGY, LiveAdapter()).asgi) as client:
        reply = await client.get("/api/topology")
    assert reply.status_code == 200
    assert msgspec.json.decode(reply.content, type=Topology) == TOPOLOGY


async def test_viewer_api_threads() -> None:
    live = await filled(2, "t1")
    async with AsyncTestClient(app=ViewerApi(TOPOLOGY, live).asgi) as client:
        reply = await client.get("/api/threads")
    assert [(item["thread"], item["offset"]) for item in reply.json()] == [("t1", 2)]


async def test_viewer_api_schema() -> None:
    async with AsyncTestClient(app=ViewerApi(TOPOLOGY, LiveAdapter()).asgi) as client:
        reply = await client.get("/api/schema/openapi.json")
    assert set(reply.json()["paths"]) == {"/api/topology", "/api/threads", "/api/threads/{thread}/events"}


@pytest.mark.parametrize(
    ("query", "headers", "offsets"),
    [
        ("", {}, ["0", "1", "2"]),
        ("?after=0", {}, ["1", "2"]),
        ("?after=0", {"last-event-id": "1"}, ["2"]),
        ("?after=1", {"last-event-id": "nope"}, ["2"]),
    ],
    ids=["whole", "after", "resumed", "bad-header"],
)
async def test_viewer_api_events_replay(query: str, headers: dict[str, str], offsets: list[str]) -> None:
    live = await filled(3)
    settings = GranianSettings(port=free_port())
    async with (
        GranianAdapter(ViewerApi(TOPOLOGY, live).asgi, settings) as server,
        httpx.AsyncClient(base_url=server.url) as client,
        client.stream("GET", f"/api/threads/t1/events{query}", headers=headers) as reply,
    ):
        assert reply.headers["content-type"].startswith("text/event-stream")
        got = await messages(reply.aiter_lines(), len(offsets))
    assert [message["id"] for message in got] == offsets
    assert {message["event"] for message in got} == {"frame"}
    assert msgspec.json.decode(got[-1]["data"])["seq"] == 2


async def test_viewer_api_events_follow() -> None:
    live = await filled(1)
    settings = GranianSettings(port=free_port())
    async with (
        GranianAdapter(ViewerApi(TOPOLOGY, live).asgi, settings) as server,
        httpx.AsyncClient(base_url=server.url) as client,
        client.stream("GET", "/api/threads/t1/events") as reply,
    ):
        lines = reply.aiter_lines()
        first = await messages(lines, 1)
        await live.send(frame(1, thread_id="t1"))
        second = await messages(lines, 1)
    assert [message["id"] for message in first + second] == ["0", "1"]


async def test_viewer_api_canvas(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>canvas</html>")
    async with AsyncTestClient(app=ViewerApi(TOPOLOGY, LiveAdapter(), dist=tmp_path).asgi) as client:
        reply = await client.get("/")
    assert reply.status_code == 200
    assert "canvas" in reply.text


async def test_viewer_api_no_canvas(tmp_path: Path) -> None:
    async with AsyncTestClient(app=ViewerApi(TOPOLOGY, LiveAdapter(), dist=tmp_path).asgi) as client:
        assert (await client.get("/")).status_code == 404
        assert (await client.get("/api/topology")).status_code == 200
