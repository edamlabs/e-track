"""tests/unit/etrack/providers/adapters/bus: the sink the bus's phase and view filters are tested against."""

from typing import ClassVar

import pytest

from etrack.models.event import EventPhase, EventView, LogView
from unit.etrack.conftest import RecordingSink


class EndsOnly(RecordingSink):
    """A sink that only takes closes, narrowed to the log view."""

    view: ClassVar[type[EventView]] = LogView
    phases: ClassVar[frozenset[EventPhase]] = frozenset({EventPhase.END})


@pytest.fixture
def ends() -> EndsOnly:
    return EndsOnly()
