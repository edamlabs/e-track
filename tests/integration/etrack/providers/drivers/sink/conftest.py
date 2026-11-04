"""tests/integration/etrack/providers/drivers/sink: a tracked deep-agent run sent to the sandbox, and what it left."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from deepagents import create_deep_agent
from langchain_core.tools import tool

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventPhase, RunEvent
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver
from support.model import call, script

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings


@dataclass(frozen=True, slots=True)
class Run:
    """What a tracked run left: its trace id, the spans it opened and every frame the live sink kept."""

    trace: str
    spans: int
    frames: int


@pytest.fixture
def project() -> str:
    """The Phoenix project the runs are read back from."""
    return "etrack-integration"


@pytest.fixture
def deep_run() -> Callable[[OtlpSettings], Awaitable[Run]]:
    """Runs a deep agent that delegates to a subagent, which calls an MCP tool — tracked into live and otlp."""
    spanned = frozenset({EventPhase.START, EventPhase.INSTANT})

    @tool
    def onto_query(query: str) -> str:
        """Run a SPARQL query."""
        return "seg:Poliza"

    async def run(settings: OtlpSettings) -> Run:
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
                tracker = Tracker(
                    EventChannel(bus, forward=None), LanggraphSourceAdapter(mcp=frozenset({"onto_query"}))
                )
                with tracker.track("e2e", {}) as tracked:
                    await agent.ainvoke(
                        {"messages": [("user", "¿qué es una póliza?")]}, tracked.config, stream_mode="messages"
                    )
            assert bus.dropped == {}
            assert bus.failed == {}
            assert live.offset("e2e") == len(kept)
        return Run(trace=tracked.scope.run_id, spans=sum(event.phase in spanned for event in kept), frames=len(kept))

    return run
