"""tests/integration/etrack/providers/drivers/sink/declared: 0.6's run-level keys as Phoenix reads them back.

A run declares what it took in and published, two model calls spend under one node and a pricer prices them; Phoenix
must show the run's words on its root span (`input.value`, `output.value`), the totals under etrack's own keys, and
token counts only where the model calls are — never summed twice."""

from typing import TYPE_CHECKING, Any

import pytest
from langgraph.graph import END, START, MessagesState

from etrack.infra.config.providers import OtlpTarget
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.logic.handle import run
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver
from support.graph import state_graph
from support.model import script, think

if TYPE_CHECKING:
    from support.sandbox import Sandbox

pytestmark = pytest.mark.integration


def _spoken() -> Any:
    async def speak(state: MessagesState) -> dict[str, Any]:
        draft = await script(think("r", "borrador", input_tokens=10, output_tokens=2, total_tokens=12)).ainvoke([])
        answer = await script(think("r", "respuesta", input_tokens=20, output_tokens=3, total_tokens=23)).ainvoke(
            [draft]
        )
        run.declare(output=str(answer.text))
        return {"messages": [answer]}

    graph = state_graph(MessagesState)
    graph.add_node("speak", speak)
    graph.add_edge(START, "speak")
    graph.add_edge("speak", END)
    return graph.compile()


async def test_phoenix_reads_the_declared_run(sandbox: Sandbox, project: str) -> None:
    target = {"phoenix": OtlpTarget(endpoint=sandbox.phoenix)}
    async with OtlpDriver(targets=target, attributes={"openinference.project.name": project}) as otlp:
        bus = AnyioAdapter()
        bus.subscribe(otlp)
        async with bus:
            tracker = Tracker(
                EventChannel(bus, forward=None), LanggraphSourceAdapter(), pricer=lambda model, usage: 0.5
            )
            with tracker.track("declared", {}) as tracked:
                run.declare(input="¿qué cubre mi póliza?")
                await _spoken().ainvoke({"messages": [("user", "¿qué cubre mi póliza?")]}, tracked.config)
        assert await otlp.flush()
    spans = await sandbox.spans(project, tracked.scope.run_id, least=4)
    (root,) = [span for span in spans if not span["parent_id"]]
    said = root["attributes"]
    assert (said["input.value"], said["output.value"], said["etrack.outcome"]) == (
        "¿qué cubre mi póliza?",
        "respuesta",
        "completed",
    )
    assert '"content":"respuesta"' in said["gen_ai.output.messages"]
    assert (said["etrack.usage.input_tokens"], said["etrack.usage.cost_usd"]) == (30, 1.0)
    ### token counts live on the model calls alone: a backend summing the trace counts each call once.
    counted = [span["attributes"].get("llm.token_count.prompt") for span in spans]
    assert sorted(count for count in counted if count is not None) == [10, 20]
