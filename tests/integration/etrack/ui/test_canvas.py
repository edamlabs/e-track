"""tests/integration/etrack/ui/canvas: the declared graph stays whole and still while a run lights it, live and replayed."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from integration.etrack.ui.conftest import Open, Run

pytestmark = pytest.mark.integration

MODEL = "rgb(57, 135, 229)"
ACTION = "rgb(217, 89, 38)"
STEP = "rgb(123, 138, 150)"


async def test_canvas_live_run_lights_a_still_graph(served: tuple[Run, Open, frozenset[str]]) -> None:
    run, open_canvas, declared = served
    canvas = await open_canvas()
    await canvas.drawn(len(declared))
    await canvas.watch()
    await run()
    await canvas.settled("llm 2")
    samples = await canvas.samples()
    ### the whole record, not one frame: no node ever added, dropped or hidden, the view never refitted.
    assert {frozenset(sample.ids) for sample in samples} == {declared}
    assert max(sample.hidden for sample in samples) == 0
    assert len({sample.viewport for sample in samples}) == 1
    assert any("tools" in sample.running for sample in samples)
    assert await canvas.text("tools", "now") == ""
    assert await canvas.text("tools", "counts") == "subagent 1"
    assert await canvas.arcs("hot") == 1
    assert await canvas.arcs("walked") >= 3


async def test_canvas_families_on_the_borders(served: tuple[Run, Open, frozenset[str]]) -> None:
    run, open_canvas, declared = served
    await run()
    canvas = await open_canvas()
    await canvas.drawn(len(declared))
    assert (await canvas.border("model"), await canvas.border("tools")) == (MODEL, ACTION)
    assert await canvas.border("PatchToolCallsMiddleware.before_agent") == STEP
    assert (await canvas.text("model", "kind"), await canvas.text("model", "title")) == ("LLM", "Model")


async def test_canvas_replay_draws_what_live_drew(served: tuple[Run, Open, frozenset[str]]) -> None:
    run, open_canvas, declared = served
    await run()
    canvas = await open_canvas()
    await canvas.drawn(len(declared))
    await canvas.settled("llm 2")
    assert await canvas.text("model", "counts") == "llm 2"
    assert await canvas.text("tools", "counts") == "subagent 1"
    assert await canvas.arcs("hot") == 1
