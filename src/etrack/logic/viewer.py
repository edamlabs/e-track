"""logic/viewer: Viewer — the live canvas of a system: its declared graph, laid out once, and every thread it keeps.

Hand it the sink that keeps the frames (`LiveAdapter`, or any `WatchPort`) and the graph a topology adapter read; it
places the graph and builds the app. The host chooses where it lives: mounted in its own ASGI app (`viewer.app` under
any prefix) or served on a port of its own, in the same process (`GranianAdapter(viewer.app)`)."""

from typing import TYPE_CHECKING

from etrack.api.viewer import ViewerApi
from etrack.processors.layout import LayoutProcessor

if TYPE_CHECKING:
    from etrack.ports.server import Asgi
    from etrack.ports.sink import WatchPort
    from etrack.ports.topology import Topology


class Viewer:
    """One system's canvas: the topology placed on its grid, the threads read from the watched sink."""

    __slots__ = ("_api", "_topology")

    def __init__(self, watch: WatchPort, topology: Topology) -> None:
        self._topology = LayoutProcessor().place(topology)
        self._api = ViewerApi(self._topology, watch)

    @property
    def topology(self) -> Topology:
        """The declared graph as the canvas draws it: ranks, lanes and loops set."""
        return self._topology

    @property
    def app(self) -> Asgi:
        """The ASGI app: `/api/topology`, `/api/threads`, `/api/threads/{thread}/events` (SSE), the canvas at `/`."""
        return self._api.asgi
