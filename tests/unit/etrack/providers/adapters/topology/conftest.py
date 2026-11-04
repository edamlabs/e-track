"""tests/unit/etrack/providers/adapters/topology: a compiled graph with a loop to read."""

from typing import Any

import pytest
from langgraph.graph import END, START, MessagesState

from support.graph import state_graph


@pytest.fixture
def looped() -> Any:
    """`start → agent → gate`, the gate going back to `agent` or on to `end`."""

    def step(state: MessagesState) -> dict[str, Any]:
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("agent", step)
    graph.add_node("gate", step)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", "gate")
    graph.add_conditional_edges("gate", lambda state: END, {"agent": "agent", "end": END})
    return graph.compile()
