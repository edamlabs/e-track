"""tests/unit/etrack/api/viewer: the doors — topology, threads, a thread over SSE (replay, resume, follow), the canvas.

The SSE tests run against a real granian server on a free localhost port: an in-memory ASGI transport buffers the
whole response, and a stream never ends."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import msgspec
import pytest
from langchain_core.messages import AIMessage
from litestar.testing import AsyncTestClient

from etrack.api.viewer import DIST, ViewerApi
from etrack.infra.config.providers.adapters.server.granian import GranianSettings
from etrack.ports.topology import Topology
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from support.port import free_port
from support.sse import sse
from unit.etrack.conftest import frame

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path


async def test_viewer_api_topology(topology: Topology) -> None:
    async with AsyncTestClient(app=ViewerApi(topology, LiveAdapter()).asgi) as client:
        reply = await client.get("/api/topology")
    assert reply.status_code == 200
    assert msgspec.json.decode(reply.content, type=Topology) == topology


async def test_viewer_api_threads(topology: Topology, filled: Callable[[int], Awaitable[LiveAdapter]]) -> None:
    live = await filled(2)
    async with AsyncTestClient(app=ViewerApi(topology, live).asgi) as client:
        reply = await client.get("/api/threads")
    assert [(item["thread"], item["offset"]) for item in reply.json()] == [("t1", 2)]


async def test_viewer_api_schema(topology: Topology) -> None:
    async with AsyncTestClient(app=ViewerApi(topology, LiveAdapter()).asgi) as client:
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
async def test_viewer_api_events_replay(
    topology: Topology,
    filled: Callable[[int], Awaitable[LiveAdapter]],
    query: str,
    headers: dict[str, str],
    offsets: list[str],
) -> None:
    live = await filled(3)
    settings = GranianSettings(port=free_port())
    async with (
        GranianAdapter(ViewerApi(topology, live).asgi, settings) as server,
        httpx.AsyncClient(base_url=server.url) as client,
        client.stream("GET", f"/api/threads/t1/events{query}", headers=headers) as reply,
    ):
        assert reply.headers["content-type"].startswith("text/event-stream")
        got = await sse(reply.aiter_lines(), len(offsets))
    assert [message["id"] for message in got] == offsets
    assert {message["event"] for message in got} == {"frame"}
    assert msgspec.json.decode(got[-1]["data"])["seq"] == 2


async def test_viewer_api_events_follow(topology: Topology, filled: Callable[[int], Awaitable[LiveAdapter]]) -> None:
    live = await filled(1)
    settings = GranianSettings(port=free_port())
    async with (
        GranianAdapter(ViewerApi(topology, live).asgi, settings) as server,
        httpx.AsyncClient(base_url=server.url) as client,
        client.stream("GET", "/api/threads/t1/events") as reply,
    ):
        lines = reply.aiter_lines()
        first = await sse(lines, 1)
        await live.send(frame(1, thread_id="t1"))
        second = await sse(lines, 1)
    assert [message["id"] for message in first + second] == ["0", "1"]


async def test_viewer_api_events_foreign_payload(topology: Topology) -> None:
    ### a LangChain message in a payload is what a real run carries: the stream encodes it, never dies on it.
    live = LiveAdapter()
    await live.send(
        frame(0, thread_id="t1", payload={"output": AIMessage("hola"), "at": datetime(2026, 11, 3, tzinfo=UTC)})
    )
    await live.send(frame(1, thread_id="t1"))
    settings = GranianSettings(port=free_port())
    async with (
        GranianAdapter(ViewerApi(topology, live).asgi, settings) as server,
        httpx.AsyncClient(base_url=server.url) as client,
        client.stream("GET", "/api/threads/t1/events") as reply,
    ):
        got = await sse(reply.aiter_lines(), 2)
    assert [message["id"] for message in got] == ["0", "1"]
    assert msgspec.json.decode(got[0]["data"])["payload"]["output"]["content"] == "hola"


async def test_viewer_api_canvas(topology: Topology, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>canvas</html>")
    async with AsyncTestClient(app=ViewerApi(topology, LiveAdapter(), dist=tmp_path).asgi) as client:
        reply = await client.get("/")
    assert reply.status_code == 200
    assert "canvas" in reply.text


async def test_viewer_api_no_canvas(topology: Topology, tmp_path: Path) -> None:
    async with AsyncTestClient(app=ViewerApi(topology, LiveAdapter(), dist=tmp_path).asgi) as client:
        assert (await client.get("/")).status_code == 404
        assert (await client.get("/api/topology")).status_code == 200


async def test_viewer_api_schema_file_is_the_contract() -> None:
    ### the canvas's types are generated from ui/schema.json: it must still say what the API sends (`make ui-types`).
    committed = (DIST.parent / "schema.json").read_bytes()
    assert committed == msgspec.json.format(msgspec.json.encode(ViewerApi.schema()), indent=2) + b"\n"
