"""tests/benchmark/etrack/logic: how many emissions a benchmark times, and what each may cost the producer."""

import pytest


@pytest.fixture
def rounds() -> int:
    return 2000


@pytest.fixture
def budget_us() -> float:
    """A token stream at 200 tokens/s leaves 5 ms per token: the producer's share must be a sliver of it."""
    return 100.0
