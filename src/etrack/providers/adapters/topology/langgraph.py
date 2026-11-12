"""providers/adapters/topology/langgraph: LanggraphTopologyAdapter — a LangGraph graph read as its declared map.

`read` takes a compiled graph or the JSON of LangChain's `Graph.to_json()` — the interchange format agent graphs are
exported in, so a host that cannot hand over the graph object (another process, a file) still draws it. From a compiled
graph, `get_graph(xray=True)` opens compiled subgraphs into their own nodes (`agent:model`), so a deep agent mounted as
a node shows its inner steps. `__start__` and `__end__` stay as nodes: a canvas draws where a run enters and leaves. A
subagent a deep agent launches through a tool is not declared anywhere — it appears only in the live span tree. A node
declared with `metadata={"label": …}` carries that label: what a person reads on the canvas, the name left intact.

A node that routes by returning `Command` declares nothing LangGraph can draw unless it says where it may go
(`destinations=` on `add_node`, or a `Command[Literal[...]]` return annotation): LangGraph then draws it to `__end__`
and leaves its targets unreached. The map cannot be guessed; the nodes no arc reaches are named in a warning instead."""

from typing import Any, ClassVar, Final, Self

import msgspec
from langgraph.constants import END, START

from etrack.infra.errors import SourceError
from etrack.infra.logger import logger
from etrack.models.event import EventKind
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode

XRAY: Final[bool] = True
### the metadata key a node's human label is declared under: `add_node("plan", fn, metadata={"label": "Plan"})`.
LABEL: Final[str] = "label"
### the metadata key a node's nature is declared under, an `EventKind` value: `metadata={"kind": "tool"}`.
KIND: Final[str] = "kind"


class GraphNode(msgspec.Struct, frozen=True, kw_only=True):
    """A node of `Graph.to_json()`: its id, its data — the runnable's description, a name, or nothing — and metadata."""

    id: str
    data: Any = None
    metadata: dict[str, Any] | None = None


class GraphEdge(msgspec.Struct, frozen=True, kw_only=True):
    """An arc of `Graph.to_json()`: its ends, the branch name a router gave it, and whether a router chooses it."""

    source: str
    target: str
    data: Any = None
    conditional: bool = False


class GraphJson(msgspec.Struct, frozen=True, kw_only=True):
    """`Graph.to_json()` as it is exported: nodes and edges."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


class LanggraphTopologyAdapter:
    """Reads any compiled LangGraph graph; holds nothing between reads."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("langgraph", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    __slots__ = ()

    ##### PRIVATE #####

    @staticmethod
    def _read_drawable(graph: object) -> Any:
        match getattr(graph, "get_graph", None):
            case None:
                msg = f"langgraph: {type(graph).__name__} is not a compiled graph (no get_graph)"
                raise SourceError(msg)
            case drawable:
                return drawable(xray=XRAY)

    @staticmethod
    def _read_name(node: GraphNode) -> str:
        """A node's name in the export: the runnable's own name, a bare string, or its id."""
        match node.data:
            case {"name": str() as name}:
                return name
            case str() as name if name:
                return name
            case _:
                return node.id

    @staticmethod
    def _read_label(metadata: dict[str, Any] | None) -> str:
        """The label a node was declared with, or none."""
        return str((metadata or {}).get(LABEL) or "")

    @staticmethod
    def _read_kind(metadata: dict[str, Any] | None) -> EventKind:
        """The nature a node was declared with, or `NODE`; a value outside the vocabulary is refused."""
        match (metadata or {}).get(KIND):
            case None:
                return EventKind.NODE
            case str() as kind if kind in EventKind:
                return EventKind(kind)
            case other:
                msg = f"langgraph: node kind {other!r} is none of {sorted(EventKind)}"
                raise SourceError(msg)

    @staticmethod
    def _read_arcs(arcs: Any) -> tuple[TopologyEdge, ...]:
        """The arcs of either reading — LangChain's `Edge` or the export's — under one id scheme."""
        return tuple(
            TopologyEdge(
                id=f"{arc.source}>{arc.target}:{index}",
                source=arc.source,
                target=arc.target,
                conditional=bool(arc.conditional),
                label=str(arc.data or ""),
            )
            for index, arc in enumerate(arcs)
        )

    @classmethod
    def _read_json(cls, graph: dict[str, Any]) -> Topology:
        try:
            exported = msgspec.convert(graph, GraphJson)
        except msgspec.ValidationError as failure:
            msg = f"langgraph: not the JSON of Graph.to_json() — {failure}"
            raise SourceError(msg) from failure
        nodes = tuple(
            TopologyNode(
                id=node.id,
                name=cls._read_name(node),
                label=cls._read_label(node.metadata),
                kind=cls._read_kind(node.metadata),
                entry=node.id == START,
                exit=node.id == END,
            )
            for node in exported.nodes
        )
        return Topology(nodes=nodes, edges=cls._read_arcs(exported.edges))

    def _read_compiled(self, graph: object) -> Topology:
        drawn = self._read_drawable(graph)
        nodes = tuple(
            TopologyNode(
                id=key,
                name=str(node.name),
                label=self._read_label(node.metadata),
                kind=self._read_kind(node.metadata),
                entry=key == START,
                exit=key == END,
            )
            for key, node in drawn.nodes.items()
        )
        return Topology(nodes=nodes, edges=self._read_arcs(drawn.edges))

    @staticmethod
    def _read_unreached(topology: Topology) -> None:
        reached = {edge.target for edge in topology.edges}
        unreached = sorted(node.id for node in topology.nodes if not node.entry and node.id not in reached)
        _ = unreached and logger.warning(
            "topology nodes unreached",
            source="langgraph",
            nodes=unreached,
            remedy="a node routing by Command declares where it goes: destinations=… or Command[Literal[...]]",
        )

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        logger.info("topology opened", source="langgraph")
        return self

    async def __aexit__(self, *exc: object) -> None:
        logger.info("topology closed", source="langgraph")

    async def health(self) -> bool:
        """Always ready: the adapter holds no resource."""
        return True

    def read(self, graph: object) -> Topology:
        """The declared nodes and arcs, unplaced, from a compiled graph or the JSON of its `Graph.to_json()`; an arc's
        label is the router's branch name when it has one; the nodes no arc reaches are named in a warning."""
        match graph:
            case dict() as exported:
                topology = self._read_json(exported)
            case _:
                topology = self._read_compiled(graph)
        self._read_unreached(topology)
        return topology
