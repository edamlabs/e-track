"""tests/unit/etrack/api: what the viewer's doors are served — a two-node topology and a live sink already holding frames."""

from typing import TYPE_CHECKING

import pytest

from etrack.ports.topology import Topology, TopologyEdge, TopologyNode
from etrack.providers.adapters.sink.live import LiveAdapter
from unit.etrack.conftest import frame

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@pytest.fixture
def topology() -> Topology:
    return Topology(
        nodes=(TopologyNode(id="a", name="a", entry=True), TopologyNode(id="b", name="b", rank=1)),
        edges=(TopologyEdge(id="a>b:0", source="a", target="b"),),
        ranks=2,
        lanes=1,
    )


@pytest.fixture
def filled() -> Callable[[int], Awaitable[LiveAdapter]]:
    """A live sink holding `count` frames of thread `t1`."""

    async def fill(count: int) -> LiveAdapter:
        live = LiveAdapter()
        _ = [await live.send(frame(seq, thread_id="t1")) for seq in range(count)]
        return live

    return fill
