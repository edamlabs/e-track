"""ports/sink: a client of the event stream — it declares the view it reads and the phases it wants, and takes views.

A sink never sees the whole record: the bus narrows each event onto the sink's `view` before handing it over, and
skips the phases the sink did not ask for before queueing — a sink that ignores token deltas never pays for them.

A remote sink signs its requests through a `SignerPort` and tells its refusals apart (`Refusal`): worth another attempt,
or final. A sink that keeps what it took may also be watched: `WatchPort` replays a thread's frames past a cursor, then follows
them live, and lists the threads it keeps — what a viewer reads, whatever sink keeps the frames."""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

import msgspec

from etrack.models.event import RunEvent
from etrack.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from etrack.models.event import EventPhase, EventView


##### VALUES #####
class LiveFrame(msgspec.Struct, frozen=True, kw_only=True):
    """A frame as a watcher receives it: its place in the thread, and the event."""

    offset: int
    event: RunEvent


class Refusal(msgspec.Struct, frozen=True, kw_only=True):
    """Why a remote system did not take what it was sent: the status (0 when the network failed), the reason in its own
    words, and whether trying again could change it (`final`: never)."""

    status: int
    reason: str
    final: bool


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
class SignerPort(Protocol):
    """What signs a request to a remote sink: the headers for the next one — a token refreshed when due, an identity of
    the host's own. The configured `Auth` meets it; a host hands its own to a driver."""

    async def headers(self) -> Mapping[str, str]: ...


@runtime_checkable
class WatchPort(Protocol):
    """A thread followed live: its frames past `after`, then every new one; and the threads there are to follow."""

    def watch(self, thread: str, after: int = -1) -> AsyncIterator[LiveFrame]: ...

    def threads(self) -> tuple[LiveSummary, ...]: ...
