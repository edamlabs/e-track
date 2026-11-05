"""tests/unit/etrack/providers/adapters/bus/anyio: fan-out — order, isolation, drops, selects, threads, drain."""

import asyncio
import threading
import time
from typing import TYPE_CHECKING

import anyio
import msgspec
import pytest

from etrack.infra.config.providers import AnyioConfig
from etrack.infra.errors import BusError
from etrack.models.event import EventPhase, LogView, RunEvent
from etrack.ports.bus import BusPort
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from support.wait import eventually
from unit.etrack.conftest import BrokenSink, RecordingSink, SlowSink, frame

if TYPE_CHECKING:
    from unit.etrack.providers.adapters.bus.conftest import EndsOnly


async def test_anyio_meets_port() -> None:
    assert isinstance(AnyioAdapter(), BusPort)


async def test_anyio_delivers_in_order(recording: RecordingSink) -> None:
    bus = AnyioAdapter()
    bus.subscribe(recording)
    async with bus:
        _ = [bus.publish(frame(seq)) for seq in range(50)]
    assert [view.seq for view in recording.views] == list(range(50))  # ty: ignore[unresolved-attribute]


async def test_anyio_subscribe_after_open(recording: RecordingSink) -> None:
    async with AnyioAdapter() as bus:
        bus.subscribe(recording)
        bus.publish(frame())
    assert len(recording.views) == 1


async def test_anyio_phases_and_view(ends: EndsOnly) -> None:
    async with AnyioAdapter() as bus:
        bus.subscribe(ends)
        bus.publish(frame(0, EventPhase.START))
        bus.publish(frame(1, EventPhase.END))
    assert [type(view) for view in ends.views] == [LogView]


async def test_anyio_broken_sink_isolated(recording: RecordingSink) -> None:
    async with AnyioAdapter() as bus:
        bus.subscribe(BrokenSink())
        bus.subscribe(recording)
        _ = [bus.publish(frame(seq)) for seq in range(3)]
    assert len(recording.views) == 3
    assert bus.failed == {"broken": 3}


async def test_anyio_slow_sink_never_blocks() -> None:
    slow = SlowSink()
    async with AnyioAdapter(**AnyioConfig(capacity=5)) as bus:
        bus.subscribe(slow)
        began = time.perf_counter()
        _ = [bus.publish(frame(seq)) for seq in range(100)]
        spent = time.perf_counter() - began
    assert spent < 0.05
    assert bus.dropped["slow"] > 0
    assert len(slow.views) + bus.dropped["slow"] == 100


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [(lambda event: event, 2), (lambda event: None, 0), (lambda event: event if event.seq else None, 1)],
    ids=["keep", "drop", "pick"],
)
async def test_anyio_select(recording: RecordingSink, verdict: object, expected: int) -> None:
    async with AnyioAdapter() as bus:
        bus.subscribe(recording, select=verdict)  # ty: ignore[invalid-argument-type]
        bus.publish(frame(0))
        bus.publish(frame(1))
    assert len(recording.views) == expected


async def test_anyio_select_transforms(recording: RecordingSink) -> None:
    def rename(event: RunEvent) -> RunEvent:
        return msgspec.structs.replace(event, name="renamed")

    async with AnyioAdapter() as bus:
        bus.subscribe(recording, select=rename)
        bus.publish(frame())
    assert recording.views[0].name == "renamed"  # ty: ignore[unresolved-attribute]


async def test_anyio_foreign_thread(recording: RecordingSink) -> None:
    async with AnyioAdapter() as bus:
        bus.subscribe(recording)
        worker = threading.Thread(target=lambda: [bus.publish(frame(seq)) for seq in range(10)])
        worker.start()
        await anyio.to_thread.run_sync(worker.join)
        await anyio.sleep(0.01)
    assert sorted(view.seq for view in recording.views) == list(range(10))  # ty: ignore[unresolved-attribute]


async def test_anyio_repeated_names(recording: RecordingSink) -> None:
    async with AnyioAdapter() as bus:
        bus.subscribe(BrokenSink())
        bus.subscribe(BrokenSink())
        bus.publish(frame())
    assert bus.failed == {"broken": 1, "broken#1": 1}


async def test_anyio_publish_closed() -> None:
    with pytest.raises(BusError, match="not open"):
        AnyioAdapter().publish(frame())


async def test_anyio_health() -> None:
    bus = AnyioAdapter()
    assert not await bus.health()
    async with bus:
        assert await bus.health()
    assert not await bus.health()


async def test_anyio_health_supervisor_dead() -> None:
    async with AnyioAdapter() as bus:
        supervisor = bus._supervisor
        assert supervisor is not None
        supervisor.cancel()
        await asyncio.wait({supervisor})
        assert not await bus.health()
        ### the dead supervisor is the exit's to report: closing re-raises its cancellation.
        with pytest.raises(asyncio.CancelledError):
            await bus.__aexit__(None, None, None)


async def test_anyio_enter_supervisor_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> None:
        msg = "no group"
        raise RuntimeError(msg)

    monkeypatch.setattr(anyio, "create_task_group", refuse)
    bus = AnyioAdapter()
    with pytest.raises(BusError, match="before the bus opened"):
        await bus.__aenter__()
    assert not await bus.health()


async def test_anyio_exit_twice() -> None:
    bus = AnyioAdapter()
    await bus.__aexit__(None, None, None)
    assert bus.dropped == {}


async def test_anyio_enter_exit_in_different_tasks(recording: RecordingSink) -> None:
    bus = AnyioAdapter()
    bus.subscribe(recording)
    await asyncio.create_task(bus.__aenter__())
    _ = [bus.publish(frame(seq)) for seq in range(20)]
    await asyncio.create_task(bus.__aexit__(None, None, None))
    assert [view.seq for view in recording.views] == list(range(20))  # ty: ignore[unresolved-attribute]
    assert not await bus.health()


async def test_anyio_subscribe_from_foreign_thread(recording: RecordingSink) -> None:
    async with AnyioAdapter() as bus:
        await anyio.to_thread.run_sync(bus.subscribe, recording)
        await anyio.sleep(0.01)
        bus.publish(frame())
    assert len(recording.views) == 1


async def test_anyio_sinks_deliver_in_parallel(recording: RecordingSink) -> None:
    slow = SlowSink()
    async with AnyioAdapter() as bus:
        bus.subscribe(slow)
        bus.subscribe(recording)
        _ = [bus.publish(frame(seq)) for seq in range(20)]
        ### the fast sink has everything while the slow one is still at its first views: workers never wait on each other.
        await eventually(lambda: len(recording.views) == 20)
        assert len(slow.views) < 20
    assert len(slow.views) == 20
