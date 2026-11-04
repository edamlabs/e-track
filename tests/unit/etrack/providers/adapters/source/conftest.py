"""tests/unit/etrack/providers/adapters/source: a source bound to a fold on a fixed scope, and a one-node agent to run."""

from typing import TYPE_CHECKING, Any, Protocol

import pytest
from langgraph.graph import END, START, MessagesState

from etrack.models.event import RunEvent, RunScope
from etrack.processors.fold import FoldProcessor
from support.graph import state_graph
from unit.etrack.conftest import RUN

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.runnables import RunnableConfig

    from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
    from support.model import ScriptedModel


class Bound(Protocol):
    def __call__(
        self, source: LanggraphSourceAdapter, config: RunnableConfig | None = None
    ) -> tuple[list[RunEvent], RunnableConfig]: ...


type AgentGraph = Callable[[ScriptedModel], Any]


@pytest.fixture
def scope() -> RunScope:
    return RunScope(run_id=RUN, thread_id="t1")


@pytest.fixture
def bound(scope: RunScope) -> Bound:
    """Binds a source to a fold on the scope: the frames it emits and the config that carries its handler."""

    def bind(
        source: LanggraphSourceAdapter, config: RunnableConfig | None = None
    ) -> tuple[list[RunEvent], RunnableConfig]:
        emitted: list[RunEvent] = []
        fold = FoldProcessor(scope, emitted.append)
        return emitted, source.bind(fold, scope, config or {})

    return bind


@pytest.fixture
def agent_graph() -> AgentGraph:
    """`start → agent → end`, the agent node answering with what the model says."""

    def build(model: ScriptedModel) -> Any:
        async def agent(state: MessagesState) -> dict[str, Any]:
            return {"messages": [await model.ainvoke(state["messages"])]}

        graph = state_graph(MessagesState)
        graph.add_node("agent", agent)
        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)
        return graph.compile()

    return build
