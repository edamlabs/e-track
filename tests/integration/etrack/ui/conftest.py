"""tests/integration/etrack/ui: the canvas watched by a real browser while a deep agent runs under it.

A deep agent delegates to a subagent whose tool sleeps, so the outer `tools` node is lit long enough for the sampler
to see it. The viewer is served by granian on a free port; chromium opens the canvas on the run's thread before the
run starts — the live path — and a second page opens it after the run — the replay path."""

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from deepagents import create_deep_agent
from langchain_core.tools import tool
from playwright.async_api import async_playwright

from etrack.infra.config.providers import GranianConfig
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.logic.viewer import Viewer
from etrack.models.event import EventKind
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter
from support.canvas import Canvas
from support.hosts import HOSTS
from support.model import call, script
from support.port import free_port

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from playwright.async_api import Browser, Page

type Run = Callable[..., Awaitable[None]]
type Open = Callable[..., Awaitable[Canvas]]

THREAD = "canvas"
SLOW = 0.8


@pytest.fixture
def canvas_agent() -> Callable[[], Any]:
    """Builds a deep agent whose subagent's tool takes `SLOW` seconds."""

    @tool
    async def onto_query(query: str) -> str:
        """Run a SPARQL query."""
        await asyncio.sleep(SLOW)
        return "seg:Poliza"

    def build() -> Any:
        return create_deep_agent(
            model=script(
                call("task", "c1", subagent_type="ontologo", description="resolve Poliza"),
                call("onto_query", "c2", query="SELECT *"),
                "Poliza es seg:Poliza",
                "listo",
            ),
            subagents=[
                {"name": "ontologo", "description": "ontología", "system_prompt": "ontólogo", "tools": [onto_query]}
            ],
        )

    return build


@pytest.fixture
async def browser() -> AsyncIterator[Browser]:
    """Headless chromium for the test."""
    async with async_playwright() as playwright:
        launched = await playwright.chromium.launch()
        yield launched
        await launched.close()


@pytest.fixture
def host(request: pytest.FixtureRequest) -> str:
    """The web app the viewer lives in: `bare` unless a test parametrizes it indirectly."""
    return getattr(request, "param", "bare")


@pytest.fixture
async def served(
    canvas_agent: Callable[[], Any], browser: Browser, host: str
) -> AsyncIterator[tuple[Run, Open, frozenset[str]]]:
    """The agent's run on `THREAD`, a way to open the canvas on it — `open(width, height)` — and the declared ids."""
    async with LiveAdapter() as live:
        bus = AnyioAdapter()
        bus.subscribe(live)
        async with bus:
            tracker = Tracker(EventChannel(bus, forward=None), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
            topology = LanggraphTopologyAdapter().read(canvas_agent())
            viewer = Viewer(
                watch=live,
                topology=topology,
                labels={"model": "Model", "tools": "Tools"},
                kinds={"model": EventKind.LLM, "tools": EventKind.TOOL},
            )
            pages: list[Page] = []
            app, prefix = HOSTS[host](viewer.app)
            async with GranianAdapter(app, **GranianConfig(port=free_port())) as server:

                async def run(thread: str = THREAD) -> None:
                    with tracker.track(thread, {}) as tracked:
                        await canvas_agent().ainvoke({"messages": [("user", "¿qué es una póliza?")]}, tracked.config)

                async def open_canvas(width: int = 1280, height: int = 900, thread: str = THREAD) -> Canvas:
                    page = await browser.new_page(viewport={"width": width, "height": height})
                    pages.append(page)
                    await page.goto(f"{server.url}{prefix}/?thread={thread}")
                    return Canvas(page)

                yield run, open_canvas, frozenset(node.id for node in topology.nodes)
                ### a page holds its event stream open: closed first, so the server can drain and stop.
                _ = [await page.close() for page in pages]
