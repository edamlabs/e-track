"""tests/unit/etrack/providers/drivers/sink: in-memory OTLP exporters and a small run (a run span, an LLM under it) to send."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from etrack.infra.config.providers.drivers.sink.http import HttpSettings
from etrack.models.event import EventKind, EventPhase, ModelRef, Usage
from unit.etrack.conftest import RUN, frame

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    type Configure = Callable[..., HttpSettings]

    from etrack.providers.drivers.sink.otlp import OtlpDriver


@pytest.fixture
def root() -> str:
    """The run span: its id is the run's, which is also the trace id."""
    return RUN


@pytest.fixture
def child() -> str:
    return "0" * 16 + "a" * 16


@pytest.fixture
def spans() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def logs() -> InMemoryLogRecordExporter:
    return InMemoryLogRecordExporter()


@pytest.fixture
def run_tree(root: str, child: str) -> Callable[[OtlpDriver], Awaitable[None]]:
    """Sends a run `deeptrack` holding one LLM call `gemini` to a driver: four frames, both spans closed."""

    async def send(driver: OtlpDriver) -> None:
        await driver.send(frame(0, EventPhase.START, id=root, kind=EventKind.RUN, name="deeptrack"))
        await driver.send(
            frame(
                1,
                EventPhase.START,
                id=child,
                parent=root,
                kind=EventKind.LLM,
                name="gemini",
                model=ModelRef(provider="google", name="gemini-2.5-flash", params={"temperature": 0.1}),
                payload={"input": [{"role": "human", "content": "hi"}]},
            )
        )
        await driver.send(
            frame(
                2,
                EventPhase.END,
                id=child,
                parent=root,
                kind=EventKind.LLM,
                name="gemini",
                usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
                payload={"text": "hola"},
            )
        )
        await driver.send(frame(3, EventPhase.END, id=root, kind=EventKind.RUN, name="deeptrack"))

    return send


@pytest.fixture
def settings() -> Configure:
    """`settings(url, **fields)`: an HTTP sink's settings — no timer in the way, a backoff of a millisecond."""

    def build(url: str, **fields: Any) -> HttpSettings:
        return HttpSettings(endpoint=url, flush=timedelta(seconds=30), backoff=timedelta(milliseconds=1), **fields)

    return build
