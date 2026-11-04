"""tests/benchmark/etrack/logic/channel: what one emission costs the producer — validate, publish, forward."""

import statistics
import time

import pytest

from etrack.logic.channel import EventChannel
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from unit.etrack.conftest import RecordingSink, frame


@pytest.mark.slow
async def test_channel_emit_cost(rounds: int, budget_us: float) -> None:
    sink = RecordingSink()
    async with AnyioAdapter() as bus:
        bus.subscribe(sink)
        channel = EventChannel(bus, forward=None)
        events = [frame(seq) for seq in range(rounds)]
        spent = [(time.perf_counter_ns(), channel.emit(event), time.perf_counter_ns()) for event in events]
    costs = sorted((end - begin) / 1000 for begin, _, end in spent)
    p50, p99 = statistics.median(costs), costs[int(len(costs) * 0.99)]
    print(f"emit p50={p50:.1f}µs p99={p99:.1f}µs over {rounds}")  # noqa: T201 — a benchmark reports its numbers
    assert p50 < budget_us
