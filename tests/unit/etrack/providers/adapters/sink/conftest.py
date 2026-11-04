"""tests/unit/etrack/providers/adapters/sink: reading a live sink the way a watcher does."""

from typing import TYPE_CHECKING

import anyio
import pytest

from etrack.ports.sink import LiveFrame
from etrack.providers.adapters.sink.live import LiveAdapter

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

type Take = Callable[[LiveAdapter, str, int, int], Awaitable[list[LiveFrame]]]


@pytest.fixture
def take() -> Take:
    """The next `count` frames a watcher of `thread` sees after `after`, within a second."""

    async def watch(live: LiveAdapter, thread: str, after: int, count: int) -> list[LiveFrame]:
        seen: list[LiveFrame] = []
        with anyio.fail_after(1):
            async for each in live.watch(thread, after):
                seen.append(each)
                if len(seen) == count:
                    break
        return seen

    return watch
