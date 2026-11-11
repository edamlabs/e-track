"""ports/bus: the fan-out between the channel and the sinks — publish never waits, each sink is served on its own.

`publish` returns at once from any thread: a full sink drops the event and counts it, it never slows the producer. A
subscription may carry a `Select`, the project's policy for that sink: the event as is, transformed, or `None` to
leave it out — and a `Redact`, that sink's own mask over what the frame carried (applied before the select). Both run on
the sink's own worker, never on the producer's path. A tracker with no mask of its own and a mask per subscription is
the way one sink receives clear text while the others never do."""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from etrack.models.event import Redact, RunEvent
from etrack.ports.provider import Provider

if TYPE_CHECKING:
    from etrack.ports.sink import SinkPort

type Select = Callable[[RunEvent], RunEvent | None]


@runtime_checkable
class BusPort(Provider, Protocol):
    """Publish without waiting, subscribe a sink with its policy, and count what each sink lost."""

    def publish(self, event: RunEvent) -> None: ...

    def subscribe(self, sink: SinkPort, select: Select | None = None, *, redact: Redact | None = None) -> None: ...

    @property
    def dropped(self) -> Mapping[str, int]: ...
