"""tests/unit/etrack/ops/prometheus: class names as metric names."""

import pytest

from etrack.ops.prometheus import prometheus_snake


@pytest.mark.parametrize(
    ("name", "snake"),
    [("BoundaryCrossed", "boundary_crossed"), ("HTTPRefused", "http_refused"), ("Handed", "handed"), ("A", "a")],
)
async def test_prometheus_snake(name: str, snake: str) -> None:
    assert prometheus_snake(name) == snake
