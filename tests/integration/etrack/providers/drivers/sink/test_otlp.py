"""tests/integration/etrack/providers/drivers/sink/otlp: a real deep-agent run, end to end, into the sandbox services.

The run goes source → fold → channel → bus → live + otlp; the session fixture brought the sandbox up. The collector
proves the wire — the span tree and the log records, read back from its OTLP/JSON files by the run's trace id; Phoenix
proves the dialect — the OpenInference kinds the driver writes, read back as Phoenix interprets them."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import pytest
from deepagents import create_deep_agent
from langchain_core.tools import tool

from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventKind, EventPhase, RunEvent
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver
from support.model import call, script

if TYPE_CHECKING:
    from support.sandbox import Sandbox

pytestmark = pytest.mark.integration

PROJECT: Final[str] = "etrack-integration"
SPANNED: Final[frozenset[EventPhase]] = frozenset({EventPhase.START, EventPhase.INSTANT})


@dataclass(frozen=True, slots=True)
class Run:
    """What a tracked run left: its trace id, the spans it opened and every frame the live sink kept."""

    trace: str
    spans: int
    frames: int


async def deep_run(settings: OtlpSettings) -> Run:
    """A deep agent that delegates to a subagent, which calls an MCP tool — tracked into live and otlp."""

    @tool
    def onto_query(query: str) -> str:
        """Run a SPARQL query."""
        return "seg:Poliza"

    agent = create_deep_agent(
        model=script(
            call("task", "c1", subagent_type="ontologo", description="resuelve Poliza"),
            call("onto_query", "c2", query="SELECT *"),
            "Poliza es seg:Poliza",
            "listo",
        ),
        subagents=[
            {"name": "ontologo", "description": "ontología", "system_prompt": "ontólogo", "tools": [onto_query]}
        ],
    )
    kept: list[RunEvent] = []
    async with LiveAdapter() as live, OtlpDriver(settings) as otlp:
        bus = AnyioAdapter()
        ### the live sink's policy keeps a copy of what reached it: every frame, every phase.
        bus.subscribe(live, select=lambda event: kept.append(event) or event)
        bus.subscribe(otlp)
        async with bus:
            tracker = Tracker(EventChannel(bus, forward=None), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
            with tracker.track("e2e", {}) as run:
                await agent.ainvoke({"messages": [("user", "¿qué es una póliza?")]}, run.config, stream_mode="messages")
        assert bus.dropped == {}
        assert bus.failed == {}
        assert live.offset("e2e") == len(kept)
    return Run(trace=run.scope.run_id, spans=sum(event.phase in SPANNED for event in kept), frames=len(kept))


async def test_otlp_collector_receives_the_tree_and_its_logs(sandbox: Sandbox) -> None:
    run = await deep_run(
        OtlpSettings(targets={"collector": OtlpTarget(endpoint=sandbox.collector)}, logs=True, service="etrack-e2e")
    )
    spans = await sandbox.received("traces", run.trace, least=run.spans)
    assert len(spans) == run.spans
    assert {"ontologo", "onto_query"} <= {span["name"] for span in spans}
    ids = {span["spanId"] for span in spans}
    (root,) = [span for span in spans if not span.get("parentSpanId")]
    assert all(span["parentSpanId"] in ids for span in spans if span is not root)
    kinds = {
        attribute["value"]["stringValue"]
        for span in spans
        for attribute in span["attributes"]
        if attribute["key"] == "etrack.kind"
    }
    assert {str(EventKind.RUN), str(EventKind.SUBAGENT), str(EventKind.MCP), str(EventKind.LLM)} <= kinds
    logs = await sandbox.received("logs", run.trace, least=run.spans)
    assert len(logs) >= run.spans
    ### the live sink took every phase, deltas included.
    assert run.frames > run.spans


async def test_otlp_phoenix_reads_the_openinference_kinds(sandbox: Sandbox) -> None:
    run = await deep_run(
        OtlpSettings(
            targets={"phoenix": OtlpTarget(endpoint=sandbox.phoenix)},
            service="etrack-e2e",
            attributes={"openinference.project.name": PROJECT},
        )
    )
    spans = await sandbox.spans(PROJECT, run.trace, least=run.spans)
    assert len(spans) == run.spans
    kinds = {span["name"]: span["span_kind"] for span in spans}
    assert kinds["ontologo"] == "AGENT"
    assert kinds["onto_query"] == "TOOL"
    assert "LLM" in kinds.values()
    ids = {span["context"]["span_id"] for span in spans}
    assert all(span["parent_id"] in ids for span in spans if span["parent_id"])
