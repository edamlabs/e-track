"""tests/unit/etrack/logic: a one-node LangGraph agent for the tracker to follow, and the fields of a valid frame."""

from typing import Any

import pytest
from langgraph.graph import START, MessagesState

from support.graph import state_graph
from support.model import script
from unit.etrack.conftest import RUN


@pytest.fixture
def graph() -> Any:
    """A compiled graph whose single `agent` node answers "hola"."""
    model = script("hola")

    async def agent(state: MessagesState) -> dict[str, Any]:
        return {"messages": [await model.ainvoke(state["messages"])]}

    built = state_graph(MessagesState)
    built.add_node("agent", agent)
    built.add_edge(START, "agent")
    return built.compile()


@pytest.fixture
def keys() -> dict[str, Any]:
    """The fields of a valid frame, as a log call carries them."""
    return {"run_id": RUN, "seq": 0, "id": "s0", "kind": "node", "phase": "start"}
