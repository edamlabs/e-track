"""tests/integration/etrack/ui/mounts: one subgraph mounted twice — each mount lights its own node, never the other's."""

from typing import TYPE_CHECKING, Any

import pytest
from langgraph.graph import END, START, MessagesState

from support.graph import state_graph

if TYPE_CHECKING:
    from collections.abc import Callable

    from integration.etrack.ui.conftest import Open, Run

pytestmark = pytest.mark.integration


@pytest.fixture
def canvas_agent() -> Callable[[], Any]:
    """`first` then `second`, the same compiled subgraph, its one node `work`."""

    def build() -> Any:
        inner = state_graph(MessagesState)
        inner.add_node("work", lambda state: {})
        inner.add_edge(START, "work")
        mounted = inner.compile()
        outer = state_graph(MessagesState)
        outer.add_node("first", mounted)
        outer.add_node("second", mounted)
        outer.add_edge(START, "first")
        outer.add_edge("first", "second")
        outer.add_edge("second", END)
        return outer.compile()

    return build


async def test_mounts_each_lights_its_own(served: tuple[Run, Open, frozenset[str]]) -> None:
    run, open_canvas, declared = served
    assert {"first:work", "second:work"} <= declared
    await run()
    canvas = await open_canvas()
    await canvas.drawn(len(declared))
    await canvas.page.wait_for_function(
        """() => document.querySelector('.react-flow__node[data-id="second:work"] .stage.last') !== null"""
    )
    first, second = await canvas.classes("first:work"), await canvas.classes("second:work")
    assert "done" in first
    assert "last" not in first
    assert {"done", "last"} <= second
    assert await canvas.page.locator('.react-flow__node[data-id="second:work"] .visits').count() == 0
    ### entry → first:work walked, first:work → second:work the last one walked (hot).
    assert (await canvas.arcs("walked"), await canvas.arcs("hot")) == (1, 1)
