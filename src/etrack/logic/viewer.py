"""logic/viewer: Viewer — the live canvas of a system: its declared graph, laid out once, and every thread it keeps.

Hand it the sink that keeps the frames (`LiveAdapter`, or any `WatchPort`) and the graph a topology adapter read; it
places the graph and builds the app. `labels` names nodes for people — by node id, over any label the graph declared —
for graphs whose nodes you did not declare yourself (a library's middleware, a mounted subgraph). The host chooses where it lives: mounted in its own ASGI app (`viewer.app` under
any prefix) or served on a port of its own, in the same process (`GranianAdapter(viewer.app)`)."""

from types import MappingProxyType
from typing import TYPE_CHECKING

import msgspec

from etrack.api.viewer import ViewerApi
from etrack.processors.layout import LayoutProcessor

if TYPE_CHECKING:
    from collections.abc import Mapping

    from etrack.ports.server import Asgi
    from etrack.ports.sink import WatchPort
    from etrack.ports.topology import Topology


class Viewer:
    """One system's canvas: the topology placed on its grid, the threads read from the watched sink."""

    __slots__ = ("_api", "_topology")

    def __init__(self, watch: WatchPort, topology: Topology, labels: Mapping[str, str] = MappingProxyType({})) -> None:
        self._topology = LayoutProcessor().place(self._init_labelled(topology, labels))
        self._api = ViewerApi(self._topology, watch)

    ##### PRIVATE #####

    @staticmethod
    def _init_labelled(topology: Topology, labels: Mapping[str, str]) -> Topology:
        """The topology with the host's labels over the declared ones, matched by node id."""
        nodes = tuple(msgspec.structs.replace(node, label=labels.get(node.id, node.label)) for node in topology.nodes)
        return msgspec.structs.replace(topology, nodes=nodes)

    ############################################################

    ##### PUBLIC #####

    @property
    def topology(self) -> Topology:
        """The declared graph as the canvas draws it: ranks, lanes and loops set."""
        return self._topology

    @property
    def app(self) -> Asgi:
        """The ASGI app: `/api/topology`, `/api/threads`, `/api/threads/{thread}/events` (SSE), the canvas at `/`."""
        return self._api.asgi
