"""ports/sink: a client of the event stream — it declares the view it reads and the phases it wants, and takes views.

A sink never sees the whole record: the bus narrows each event onto the sink's `view` before handing it over, and
skips the phases the sink did not ask for before queueing — a sink that ignores token deltas never pays for them.

A sink that keeps what it took may also be watched: `WatchPort` replays a thread's frames past a cursor, then follows
them live, and lists the threads it keeps — what a viewer reads, whatever sink keeps the frames."""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

import msgspec

from etrack.models.event import RunEvent
from etrack.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from etrack.models.event import EventPhase, EventView


##### VALUES #####
class LiveFrame(msgspec.Struct, frozen=True, kw_only=True):
    """A frame as a watcher receives it: its place in the thread, and the event."""

    offset: int
    event: RunEvent


class LiveSummary(msgspec.Struct, frozen=True, kw_only=True):
    """A kept thread as a picker lists it: its next offset, its runs in the order they began, its last frame's time."""

    thread: str
    offset: int
    runs: tuple[str, ...]
    last: datetime


##### PORTS #####


@runtime_checkable
class SinkPort(Provider, Protocol):
    """A consumer of views: what it reads, which phases reach it, and the one call that delivers."""

    view: ClassVar[type[EventView]]
    phases: ClassVar[frozenset[EventPhase]]

    async def send(self, view: EventView) -> None: ...


@runtime_checkable
class WatchPort(Protocol):
    """A thread followed live: its frames past `after`, then every new one; and the threads there are to follow."""

    def watch(self, thread: str, after: int = -1) -> AsyncIterator[LiveFrame]: ...

    def threads(self) -> tuple[LiveSummary, ...]: ...
