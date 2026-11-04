"""tests/unit/etrack/processors: the fold on a fixed run scope with the frames it emits, edges to feed it, graphs to lay out."""

from typing import TYPE_CHECKING, Any

import pytest

from etrack.models.event import EventKind, RunEvent, RunScope
from etrack.ports.source import Edge
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode
from etrack.processors.fold import FoldProcessor
from unit.etrack.conftest import RUN

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def scope() -> RunScope:
    return RunScope(run_id=RUN, thread_id="t1")


@pytest.fixture
def emitted() -> list[RunEvent]:
    return []


@pytest.fixture
def fold(scope: RunScope, emitted: list[RunEvent]) -> FoldProcessor:
    return FoldProcessor(scope, emitted.append)


@pytest.fixture
def edge() -> Callable[..., Edge]:
    """An edge of span `span`: a NODE under `parent` unless told otherwise, named after the span."""

    def build(span: str, parent: str = "", kind: EventKind | None = EventKind.NODE, **fields: Any) -> Edge:
        return Edge(id=span, parent=parent, kind=kind, name=fields.pop("name", span), **fields)

    return build


@pytest.fixture
def topology() -> Callable[..., Topology]:
    """A topology from `(source, target)` arcs; nodes are the arcs' ends unless `names` lists them."""

    def build(arcs: list[tuple[str, str]], names: list[str] | None = None) -> Topology:
        ids = names or sorted({end for arc in arcs for end in arc})
        nodes = tuple(TopologyNode(id=name, name=name, entry=name == "start") for name in ids)
        edges = tuple(TopologyEdge(id=f"{a}>{b}", source=a, target=b) for a, b in arcs)
        return Topology(nodes=nodes, edges=edges)

    return build
