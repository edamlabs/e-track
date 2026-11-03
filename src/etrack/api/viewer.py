"""api/viewer: ViewerApi — the viewer's doors over HTTP: the laid-out graph, the threads, a thread live, the canvas.

`GET /api/topology` is the declared graph as placed; `GET /api/threads` the threads the watched sink keeps, the most
recently written first; `GET /api/threads/{thread}/events` a thread over Server-Sent Events — each message's `id` is
the frame's offset in the thread and its `data` the RunEvent as JSON, replayed past the cursor then followed live. The
cursor is `?after=` or, on a browser's automatic reconnect, the `Last-Event-ID` header: a reconnect misses nothing
still kept. `/` serves the canvas from `etrack/ui/dist` when the bundle is there; without it the API runs alone. The
app is plain ASGI: a host mounts it under any prefix, or GranianAdapter serves it on its own port."""

from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Final

import msgspec
from litestar import Litestar, get
from litestar.openapi import OpenAPIConfig
from litestar.params import HeaderParameter, PathParameter, QueryParameter
from litestar.response import ServerSentEvent
from litestar.response.sse import ServerSentEventMessage
from litestar.static_files import create_static_files_router

from etrack.ports.sink import LiveFrame, LiveSummary, WatchPort
from etrack.ports.topology import Topology

DIST: Final[Path] = Path(__file__).resolve().parents[1] / "ui" / "dist"
FRAME: Final[str] = "frame"


class ViewerApi:
    """The viewer's ASGI app over one laid-out topology and one watched sink."""

    __slots__ = ("_asgi", "_dist", "_topology", "_watch")

    def __init__(self, topology: Topology, watch: WatchPort, dist: Path = DIST) -> None:
        self._topology = topology
        self._watch = watch
        self._dist = dist
        self._asgi = Litestar(
            route_handlers=[
                get("/api/topology", name="topology")(self._asgi_topology),
                get("/api/threads", name="threads")(self._asgi_threads),
                get("/api/threads/{thread:str}/events", name="events")(self._asgi_events),
                *self._asgi_canvas(),
            ],
            openapi_config=OpenAPIConfig(title="e-track viewer", version="1", path="/api/schema"),
        )

    ##### PRIVATE #####

    @staticmethod
    def _events_cursor(resumed: str | None, after: int) -> int:
        """Where a stream resumes: the browser's `Last-Event-ID` when it sent one, `?after=` otherwise."""
        return int(resumed) if resumed and resumed.lstrip("-").isdigit() else after

    @staticmethod
    async def _events_stream(frames: AsyncIterator[LiveFrame]) -> AsyncGenerator[ServerSentEventMessage]:
        ### a stream is a loop by nature, alive as long as the browser listens.
        async for frame in frames:
            yield ServerSentEventMessage(data=msgspec.json.encode(frame.event).decode(), id=frame.offset, event=FRAME)

    async def _asgi_topology(self) -> Topology:
        """The declared graph, every node on its rank and lane, the arcs that close a loop marked."""
        return self._topology

    async def _asgi_threads(self) -> tuple[LiveSummary, ...]:
        """The threads the watched sink keeps, the most recently written first."""
        return self._watch.threads()

    async def _asgi_events(
        self,
        thread: Annotated[str, PathParameter()],
        after: Annotated[int, QueryParameter()] = -1,
        resumed: Annotated[str | None, HeaderParameter(name="last-event-id")] = None,
    ) -> ServerSentEvent:
        """A thread's frames past the cursor, then live, as Server-Sent Events."""
        return ServerSentEvent(self._events_stream(self._watch.watch(thread, self._events_cursor(resumed, after))))

    def _asgi_canvas(self) -> list[Any]:
        ### no bundle, no page: the API still runs, `/` answers 404.
        return (
            [create_static_files_router(path="/", directories=[self._dist], html_mode=True, name="canvas")]
            if (self._dist / "index.html").is_file()
            else []
        )

    ############################################################

    ##### PUBLIC #####

    @property
    def asgi(self) -> Litestar:
        """The ASGI app: the API under `/api`, its OpenAPI schema at `/api/schema`, the canvas at `/`."""
        return self._asgi
