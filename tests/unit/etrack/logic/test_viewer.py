"""tests/unit/etrack/logic/viewer: the canvas of a system — its graph placed once, its app answering on the API."""

from litestar.testing import AsyncTestClient

from etrack.logic.viewer import Viewer
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode
from etrack.providers.adapters.sink.live import LiveAdapter


async def test_viewer_places_and_serves() -> None:
    topology = Topology(
        nodes=(TopologyNode(id="a", name="a", entry=True), TopologyNode(id="b", name="b")),
        edges=(TopologyEdge(id="a>b", source="a", target="b"), TopologyEdge(id="b>a", source="b", target="a")),
    )
    viewer = Viewer(watch=LiveAdapter(), topology=topology)
    assert [node.rank for node in viewer.topology.nodes] == [0, 1]
    assert [edge.loop for edge in viewer.topology.edges] == [False, True]
    async with AsyncTestClient(app=viewer.app) as client:
        reply = await client.get("/api/topology")
    assert reply.json()["ranks"] == 2
