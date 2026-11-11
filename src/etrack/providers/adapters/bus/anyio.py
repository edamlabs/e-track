"""providers/adapters/bus/anyio: AnyioAdapter — one bounded stream and one worker per sink, publish never waits.

`publish` is synchronous and returns at once: on the loop's thread it queues the event on every sink that takes its
phase; from any other thread it hops onto the loop first. A full stream drops the event for that sink alone and counts
it. Each worker masks the event with the subscription's `Redact`, applies its `Select`, narrows the event onto the sink's view and awaits `send`; a
select or a sink that raises is logged and skipped, never the producer's problem nor another sink's. Leaving the bus
closes every stream, lets each worker deliver what is still queued, then stops.

A supervisor task owns the task group for the bus's whole life, so the bus is entered and left by any task: anyio
cancel scopes are task-bound, and a host (pytest-asyncio fixtures, a lifespan split across tasks) need not be one."""

import asyncio
import math
import threading
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Self, Unpack

import anyio
from anyio.streams.memory import MemoryObjectSendStream

from etrack.infra import defaults
from etrack.infra.errors import BusError
from etrack.infra.logger import logger
from etrack.models.event import RunEvent
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping

    from anyio.streams.memory import MemoryObjectReceiveStream

    from etrack.infra.config.providers import AnyioConfig
    from etrack.models.event import Redact
    from etrack.ports.bus import Select
    from etrack.ports.sink import SinkPort


@dataclass(slots=True)
class Subscription:
    """One sink, its policy, and the bounded stream between the bus and its worker."""

    name: str
    sink: SinkPort
    select: Select | None
    redact: Redact | None
    send: MemoryObjectSendStream[RunEvent]
    receive: MemoryObjectReceiveStream[RunEvent]


class AnyioAdapter:
    """The in-process fan-out: sinks subscribe before or after it opens; events reach each sink in publish order."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("anyio", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    __slots__ = ("_conf", "_dropped", "_failed", "_feed", "_loop", "_subs", "_supervisor", "_thread")

    def __init__(self, **given: Unpack[AnyioConfig]) -> None:
        """Keyword arguments as `AnyioConfig` names them; what is not given, ETRACK_BUS_* fills (`infra/defaults`)."""
        self._conf = defaults.anyio(**given)
        self._subs: list[Subscription] = []
        self._dropped: Counter[str] = Counter()
        self._failed: Counter[str] = Counter()
        self._feed: MemoryObjectSendStream[Subscription] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: int | None = None
        self._supervisor: asyncio.Task[None] | None = None

    ##### PRIVATE #####

    @property
    def _common_capacity(self) -> int:
        return self._conf["capacity"]

    def _subscribe_start(self, sub: Subscription) -> None:
        ### the group is not thread-safe and only its supervisor may spawn: a foreign thread hops onto the loop first.
        match self._feed:
            case None:
                pass
            case feed:
                _ = (
                    feed.send_nowait(sub)
                    if threading.get_ident() == self._thread
                    else self._publish_loop().call_soon_threadsafe(self._subscribe_feed, feed, sub)
                )

    def _subscribe_feed(self, feed: MemoryObjectSendStream[Subscription], sub: Subscription) -> None:
        ### a hop that lands after the bus closed finds the feed shut: the sink simply never starts.
        with suppress(anyio.ClosedResourceError):
            feed.send_nowait(sub)

    async def _open_supervise(self, feed: MemoryObjectReceiveStream[Subscription], opened: asyncio.Event) -> None:
        ### the supervisor owns the group from its own task: it ends when the feed closes and the workers have drained.
        ### the feed is entered first: a group that cannot be created still leaves it closed.
        async with feed, anyio.create_task_group() as group:
            opened.set()
            async for sub in feed:
                group.start_soon(self._subscribe_serve, sub)

    async def _enter_opened(self, supervisor: asyncio.Task[None], opened: asyncio.Event) -> None:
        ### whichever comes first: the group opened, or the supervisor ended without opening it — never a hang.
        waiter = asyncio.ensure_future(opened.wait())
        await asyncio.wait({supervisor, waiter}, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        match opened.is_set():
            case True:
                return
            case _:
                _ = self._feed and self._feed.close()
                self._feed = self._loop = self._thread = self._supervisor = None
                msg = "AnyioAdapter: the supervisor ended before the bus opened"
                raise BusError(msg) from supervisor.exception()

    async def _subscribe_serve(self, sub: Subscription) -> None:
        ### a worker is a loop by nature, alive as long as its stream: a comprehension would keep one item per event.
        async with sub.receive:
            async for event in sub.receive:
                await self._subscribe_deliver(sub, event)

    async def _subscribe_deliver(self, sub: Subscription, event: RunEvent) -> None:
        try:
            masked = event.masked(sub.redact) if sub.redact else event
            chosen = sub.select(masked) if sub.select else masked
            _ = chosen is not None and await sub.sink.send(sub.sink.view.project(chosen))
        except Exception as failure:  # noqa: BLE001 — a sink's failure is its own, never the producer's nor a sibling's
            self._failed[sub.name] += 1
            logger.warning("bus delivery failed", sink=sub.name, error=f"{type(failure).__name__}: {failure}")

    def _publish_local(self, event: RunEvent) -> None:
        _ = [self._publish_one(sub, event) for sub in self._subs if event.phase in sub.sink.phases]

    def _publish_one(self, sub: Subscription, event: RunEvent) -> None:
        try:
            sub.send.send_nowait(event)
        except anyio.WouldBlock, anyio.ClosedResourceError, anyio.BrokenResourceError:
            self._dropped[sub.name] += 1

    def _publish_loop(self) -> asyncio.AbstractEventLoop:
        match self._loop:
            case None:
                msg = "AnyioAdapter is not open: the lifespan opens it before any run"
                raise BusError(msg)
            case loop:
                return loop

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._loop = asyncio.get_running_loop()
        self._thread = threading.get_ident()
        send, feed = anyio.create_memory_object_stream[Subscription](math.inf)
        _ = [send.send_nowait(sub) for sub in self._subs]
        self._feed = send
        opened = asyncio.Event()
        self._supervisor = asyncio.create_task(self._open_supervise(feed, opened))
        await self._enter_opened(self._supervisor, opened)
        logger.info("bus opened", sinks=[sub.name for sub in self._subs], capacity=self._common_capacity)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._supervisor, self._feed:
            case asyncio.Task() as supervisor, MemoryObjectSendStream() as feed:
                ### closing the send side lets each worker drain what is queued, then end on its own.
                _ = [sub.send.close() for sub in self._subs]
                feed.close()
                try:
                    await supervisor
                finally:
                    self._feed = self._loop = self._thread = self._supervisor = None
                logger.info("bus closed", dropped=dict(self._dropped), failed=dict(self._failed))
            case _:
                return

    async def health(self) -> bool:
        """Open: the supervisor still runs its workers and publish is accepted."""
        return self._supervisor is not None and not self._supervisor.done()

    def subscribe(self, sink: SinkPort, select: Select | None = None, *, redact: Redact | None = None) -> None:
        """A sink served from now on, masked by `redact` and through `select` when given; named by its spec, numbered
        when repeated."""
        taken = sum(sub.sink.spec.name == sink.spec.name for sub in self._subs)
        name = sink.spec.name if taken == 0 else f"{sink.spec.name}#{taken}"
        send, receive = anyio.create_memory_object_stream[RunEvent](self._common_capacity)
        sub = Subscription(name=name, sink=sink, select=select, redact=redact, send=send, receive=receive)
        self._subs.append(sub)
        self._subscribe_start(sub)

    def publish(self, event: RunEvent) -> None:
        """Queue the event for every sink that takes its phase; from a foreign thread, hop onto the loop first."""
        loop = self._publish_loop()
        match threading.get_ident() == self._thread:
            case True:
                self._publish_local(event)
            case _:
                loop.call_soon_threadsafe(self._publish_local, event)

    @property
    def dropped(self) -> Mapping[str, int]:
        """Events lost per sink because its stream was full or closed."""
        return MappingProxyType(dict(self._dropped))

    @property
    def failed(self) -> Mapping[str, int]:
        """Deliveries that raised, per sink."""
        return MappingProxyType(dict(self._failed))
