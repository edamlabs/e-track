"""ports/outbox: where an item waits until it is delivered — stored before any network call, claimed, settled.

The transactional outbox, without the host's transaction: a sink appends what it must deliver, keyed by the key the
receiver deduplicates by, and only then is it sent; a relay claims what is due, and settles each claim — delivered
(`ack`, gone), tried again later (`release`), or given up (`dead`, with the reason, kept until someone `requeue`s it).
A claim is a lease: an item claimed by a relay that died is due again when its lease ends. Delivery is at least once:
the receiver's deduplication by key makes it exactly once in effect. The guarantee begins at `append` — what a run held
in memory before it ended is the host's to reconcile."""

from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import msgspec

from etrack.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


##### VALUES #####
class EntryState(StrEnum):
    """Where an item stands: waiting to be delivered (due or leased), or given up."""

    PENDING = auto()
    DEAD = auto()


class Entry(msgspec.Struct, frozen=True, kw_only=True):
    """An item in the outbox: its key, its encoded body, where it stands, how often it was tried, when it was appended,
    when it is next due, and why it last failed."""

    key: str
    item: bytes
    state: EntryState
    attempts: int
    created: datetime
    due: datetime
    reason: str = ""


##### PORT #####
@runtime_checkable
class OutboxPort(Provider, Protocol):
    """Items stored before they are sent, claimed by one relay at a time, settled one by one."""

    async def append(self, key: str, item: bytes) -> bool: ...

    async def claim(self, limit: int, lease: timedelta) -> Sequence[Entry]: ...

    async def ack(self, key: str) -> None: ...

    async def release(self, key: str, due: datetime, reason: str) -> None: ...

    async def dead(self, key: str, reason: str) -> None: ...

    async def of(self, key: str) -> Entry | None: ...

    async def requeue(self, key: str) -> bool: ...

    async def report(self) -> Mapping[EntryState, int]: ...
