"""tests/unit/etrack/providers/adapters/topology/langgraph: a compiled graph read as nodes and arcs, deep agents included."""

from typing import Any, Literal

import pytest
from deepagents import create_deep_agent
from langgraph.graph import END, START, MessagesState
from langgraph.types import Command
from structlog.testing import capture_logs

from etrack.infra.errors import SourceError
from etrack.models.event import EventKind
from etrack.ports.topology import TopologyPort
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter
from support.graph import state_graph
from support.model import script


async def test_langgraph_meets_port() -> None:
    async with LanggraphTopologyAdapter() as adapter:
        assert isinstance(adapter, TopologyPort)
        assert await adapter.health()


async def test_langgraph_reads_nodes_and_arcs(looped: Any) -> None:
    topology = LanggraphTopologyAdapter().read(looped)
    assert {node.id for node in topology.nodes} == {"__start__", "agent", "gate", "__end__"}
    entries = [node.id for node in topology.nodes if node.entry]
    exits = [node.id for node in topology.nodes if node.exit]
    assert (entries, exits) == (["__start__"], ["__end__"])
    arcs = {(edge.source, edge.target, edge.conditional, edge.label) for edge in topology.edges}
    assert ("gate", "__end__", True, "end") in arcs
    assert ("agent", "gate", False, "") in arcs


async def test_langgraph_deep_agent_nodes() -> None:
    topology = LanggraphTopologyAdapter().read(create_deep_agent(model=script("x")))
    assert {"__start__", "model", "tools", "__end__"} <= {node.id for node in topology.nodes}


async def test_langgraph_rejects_non_graph() -> None:
    with pytest.raises(SourceError, match="not a compiled graph"):
        LanggraphTopologyAdapter().read(object())


async def test_langgraph_reads_the_json_export_like_the_graph(looped: Any) -> None:
    graph = looped
    exported = LanggraphTopologyAdapter().read(graph.get_graph(xray=True).to_json())
    assert exported == LanggraphTopologyAdapter().read(graph)


async def test_langgraph_json_names() -> None:
    topology = LanggraphTopologyAdapter().read(
        {
            "nodes": [{"id": "a", "data": {"name": "agent"}}, {"id": "b", "data": "bare"}, {"id": "c"}],
            "edges": [{"source": "a", "target": "b", "data": "go", "conditional": True}],
        }
    )
    assert [node.name for node in topology.nodes] == ["agent", "bare", "c"]
    assert topology.edges[0].label == "go"


async def test_langgraph_rejects_foreign_json() -> None:
    with pytest.raises(SourceError, match=r"not the JSON of Graph\.to_json\(\)"):
        LanggraphTopologyAdapter().read({"nodes": "nope"})


async def test_langgraph_reads_declared_labels() -> None:
    def step(state: MessagesState) -> dict[str, Any]:
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("plan", step, metadata={"label": "Plan the answer"})
    graph.add_node("act", step)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", END)
    compiled = graph.compile()
    for read in (compiled, compiled.get_graph(xray=True).to_json()):
        labels = {node.id: node.label for node in LanggraphTopologyAdapter().read(read).nodes}
        assert (labels["plan"], labels["act"]) == ("Plan the answer", "")


async def test_langgraph_reads_declared_kinds() -> None:
    def step(state: MessagesState) -> dict[str, Any]:
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("think", step, metadata={"kind": "agent"})
    graph.add_node("act", step)
    graph.add_edge(START, "think")
    graph.add_edge("think", "act")
    graph.add_edge("act", END)
    compiled = graph.compile()
    for read in (compiled, compiled.get_graph(xray=True).to_json()):
        kinds = {node.id: node.kind for node in LanggraphTopologyAdapter().read(read).nodes}
        assert (kinds["think"], kinds["act"], kinds[START]) == (EventKind.AGENT, EventKind.NODE, EventKind.NODE)


async def test_langgraph_rejects_unknown_kind() -> None:
    def step(state: MessagesState) -> dict[str, Any]:
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("odd", step, metadata={"kind": "robot"})
    graph.add_edge(START, "odd")
    graph.add_edge("odd", END)
    with pytest.raises(SourceError, match="node kind 'robot'"):
        LanggraphTopologyAdapter().read(graph.compile())


def _routed(*, declared: bool) -> Any:
    def route(state: MessagesState) -> Command[Literal["a", "b"]]:
        return Command[Literal["a", "b"]](goto="b")

    def undeclared(state: MessagesState) -> Command[Any]:
        return Command(goto="b")

    graph = state_graph(MessagesState)
    graph.add_node("route", route if declared else undeclared)
    graph.add_node("a", lambda state: {})
    graph.add_node("b", lambda state: {})
    graph.add_edge(START, "route")
    graph.add_edge("a", END)
    graph.add_edge("b", END)
    return graph.compile()


@pytest.mark.parametrize(("declared", "unreached"), [(True, []), (False, [["a", "b"]])], ids=["declared", "undeclared"])
async def test_langgraph_command_destinations(declared: bool, unreached: list[list[str]]) -> None:
    with capture_logs() as lines:
        topology = LanggraphTopologyAdapter().read(_routed(declared=declared))
    arcs = {(edge.source, edge.target) for edge in topology.edges}
    assert ({("route", "a"), ("route", "b")} <= arcs) is declared
    assert [line["nodes"] for line in lines if line["event"] == "topology nodes unreached"] == unreached
