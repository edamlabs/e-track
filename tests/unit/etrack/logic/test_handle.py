"""tests/unit/etrack/logic/handle: RunHandle — the run reached from inside a node, a no-op outside, never crossed."""

import asyncio
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState
from langgraph.types import interrupt

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.logic.handle import run
from etrack.models.event import EventKind, EventPhase, Outcome
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from support.events import by
from support.graph import state_graph
from support.model import script
from unit.etrack.conftest import Collector


async def _rank() -> str:
    with run.span("rank", k=5) as span:
        await asyncio.sleep(0)
        return span


def _ranked() -> Any:
    async def retrieve(state: MessagesState) -> dict[str, Any]:
        await _rank()
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("retrieve", retrieve)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", END)
    return graph.compile()


async def test_handle_span_under_node(collector: Collector) -> None:
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}) as tracked:
        assert run.active
        await _ranked().ainvoke({"messages": []}, tracked.config)
    (node,) = by(collector.events, EventKind.NODE, EventPhase.START)
    rank = [event for event in collector.events if event.name == "rank"]
    assert [event.phase for event in rank] == [EventPhase.START, EventPhase.END]
    assert (rank[0].parent, rank[0].attributes) == (node.id, {"k": 5})


async def test_handle_outside_run() -> None:
    assert not run.active
    assert await _rank() == ""


async def test_handle_outside_graph(collector: Collector) -> None:
    ### tracked, but no LangChain runnable around the caller: the span hangs from the run's root.
    tracker = Tracker(EventChannel(collector), LanggraphSourceAdapter())
    with tracker.track("t1", {}) as tracked, tracked.fold.span("door") as door:
        await _rank()
    rank = next(event for event in collector.events if event.name == "rank")
    assert rank.parent == door


async def test_handle_sourceless_hangs_from_root(collector: Collector) -> None:
    class Bare:
        def bind(self, fold: Any, scope: Any, config: dict[str, Any]) -> dict[str, Any]:
            return config

    tracker = Tracker(EventChannel(collector), Bare())  # ty: ignore[invalid-argument-type]
    with tracker.track("t1", {}) as tracked, tracked.fold.span("root") as root:
        await _rank()
    rank = next(event for event in collector.events if event.name == "rank")
    assert rank.parent == root


async def test_handle_concurrent_runs_apart() -> None:
    tracker_a, tracker_b = Collector(), Collector()

    async def one(collector: Collector, thread: str) -> str:
        with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track(thread, {}) as tracked:
            await _ranked().ainvoke({"messages": []}, tracked.config)
            return tracked.scope.run_id

    run_a, run_b = await asyncio.gather(one(tracker_a, "a"), one(tracker_b, "b"))
    assert {event.run_id for event in tracker_a.events} == {run_a}
    assert {event.run_id for event in tracker_b.events} == {run_b}
    assert not run.active


##### DECLARED #####
def _spoken() -> Any:
    """`speak` answers and declares it; `refine` calls a model after it — the last model call is not what was said."""

    async def speak(state: MessagesState) -> dict[str, Any]:
        answer = await script("final answer").ainvoke(state["messages"])
        run.declare(output=str(answer.content))
        return {"messages": [answer]}

    async def refine(state: MessagesState) -> dict[str, Any]:
        await script("a refiner's rewrite").ainvoke(state["messages"])
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("speak", speak)
    graph.add_node("refine", refine)
    graph.add_edge(START, "speak")
    graph.add_edge("speak", "refine")
    graph.add_edge("refine", END)
    return graph.compile()


async def test_handle_declared_output_wins(collector: Collector) -> None:
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}) as tracked:
        run.declare(input="hola")
        await _spoken().ainvoke({"messages": [("user", "hola")]}, tracked.config)
    (ended,) = by(collector.events, EventKind.RUN, EventPhase.END)
    assert (ended.input, ended.output, ended.outcome) == ("hola", "final answer", Outcome.COMPLETED)


async def test_handle_undeclared_absent(collector: Collector) -> None:
    run.declare(output="nobody hears this")
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}) as tracked:
        await _ranked().ainvoke({"messages": []}, tracked.config)
    (ended,) = by(collector.events, EventKind.RUN, EventPhase.END)
    assert (ended.input, ended.output) == (None, None)


async def test_handle_interrupted_outcome(collector: Collector) -> None:
    def ask(state: MessagesState) -> dict[str, Any]:
        interrupt({"q": "?"})
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("ask", ask)
    graph.add_edge(START, "ask")
    compiled = graph.compile(checkpointer=InMemorySaver())
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}) as tracked:
        await compiled.ainvoke({"messages": []}, {**tracked.config, "configurable": {"thread_id": "t1"}})
    (ended,) = by(collector.events, EventKind.RUN, EventPhase.END)
    assert ended.outcome is Outcome.INTERRUPTED
