"""tests/unit/etrack/ops: a run id whose hex is known."""

import pytest


@pytest.fixture
def run() -> str:
    return "019a" + "0" * 12 + "8" + "f" * 15
