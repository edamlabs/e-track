"""providers/drivers/sink/http: HttpDriver — events batched to any HTTP endpoint; the base a custom driver is built on.

The bus already gives every sink its own worker, a bounded queue and a `select`: this driver adds what a remote system
needs. Events gather in a batch that leaves when it is full or when the oldest has waited `flush`; a request that
meets a network error, a 408, 425, 429 or a 5xx is retried with a doubling backoff, any other refusal is final; a batch
refused for good is sent again item by item, so one bad item costs one item. What is refused in the end is handed to
`refused` with the server's reason — never raised in the bus's way. Every request is signed by the configured `Auth`, or
by the host's own `SignerPort`. Leaving the driver sends what is left.

Handed an `OutboxPort`, the driver guarantees delivery: `send` stores each item under its `key` before any network
call, and a relay delivers what is due — a refusal worth another attempt waits the next step of `schedule` (the last
repeats), an item still undelivered past `deadline` is dead, a final refusal is dead at once, each with its reason, and
`requeue` on the outbox sends a dead item again. Delivery is at least once; the receiver deduplicates by key. The
guarantee begins when the item is stored: what a run held in memory before it ended is the host's to reconcile.
Subscribe such a driver with `Delivery.GUARANTEED`, so the bus never drops what it has not stored yet.

A custom driver subclasses it and overrides what it must, nothing else:

- `view` — the fields it reads (the bus narrows every event onto it before `send`);
- `phases` — the phases it wants (the bus skips the rest before queueing);
- `accept(view)` — whether this event is sent at all — the project's gate: it fails closed, an `accept` that reads a
  key the event does not carry (`view.attributes["app.owner"]`) refuses the event and counts it (`missing`), so a
  missing fact never passes as a default;
- `encode(view)` — the item the event becomes (a `msgspec.Struct`, a dict, anything msgspec encodes);
- `body(items)` — the request body and its content type, when the endpoint wants a shape of its own (with an outbox,
  the items it receives are the stored ones, as `msgspec.Raw`);
- `key(view, content)` — with an outbox, the key an item is stored and deduplicated by: by default, its content's hash;
- `refused(items, refusal)` — what to do with items the endpoint did not take: by default, a warning."""

import asyncio
import hashlib
from contextlib import suppress
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, Unpack

import httpx
import msgspec

from etrack.infra import defaults
from etrack.infra.auth import AuthSigner
from etrack.infra.config.providers import Encoding
from etrack.infra.errors import SinkError
from etrack.infra.logger import logger
from etrack.models.event import EventPhase, EventView, RunEvent
from etrack.ports.outbox import EntryState
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.ports.sink import Refusal, SignerPort

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from etrack.infra.config.providers import HttpConfig
    from etrack.ports.outbox import Entry, OutboxPort

PHASES: Final[frozenset[EventPhase]] = frozenset(
    {EventPhase.START, EventPhase.END, EventPhase.ERROR, EventPhase.INSTANT}
)
### the refusals worth another attempt: a timeout, too early, too many requests, and the server's own failures.
RETRIED: Final[frozenset[int]] = frozenset({408, 425, 429, 500, 502, 503, 504})
REASON: Final[int] = 200


def body_json(items: Sequence[Any]) -> tuple[bytes, str]:
    """A batch as one JSON array."""
    return msgspec.json.encode(items), "application/json"


def body_ndjson(items: Sequence[Any]) -> tuple[bytes, str]:
    """A batch as one JSON value per line."""
    return b"".join(msgspec.json.encode(item) + b"\n" for item in items), "application/x-ndjson"


BODIES: Final[Mapping[Encoding, Callable[[Sequence[Any]], tuple[bytes, str]]]] = MappingProxyType(
    {Encoding.JSON: body_json, Encoding.NDJSON: body_ndjson}
)


class DeliveryReport(msgspec.Struct, frozen=True, kw_only=True):
    """Where a driver's items stand: delivered, refused in the end, refused by the gate for a missing key, and — with an
    outbox — still pending and dead."""

    sent: int
    failed: int
    missing: int
    pending: int = 0
    dead: int = 0


class HttpDriver:
    """A batching, retrying, signed HTTP sink — use it as it is, or subclass it for a system of your own."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("http", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True)
    view: ClassVar[type[EventView]] = RunEvent
    phases: ClassVar[frozenset[EventPhase]] = PHASES

    __slots__ = (
        "_batch",
        "_client",
        "_conf",
        "_failed",
        "_given",
        "_lock",
        "_missing",
        "_nudge",
        "_outbox",
        "_sent",
        "_signer",
        "_ticker",
    )

    def __init__(
        self, *, signer: SignerPort | None = None, outbox: OutboxPort | None = None, **given: Unpack[HttpConfig]
    ) -> None:
        """Keyword arguments as `HttpConfig` names them; what is not given, ETRACK_HTTP_* fills (`infra/defaults`).
        `signer`, when given, signs every request instead of the configured `auth`; `outbox`, when given, stores every
        item before it is sent and guarantees its delivery."""
        self._conf = defaults.http(**given)
        self._given = signer
        self._outbox = outbox
        self._nudge = asyncio.Event()
        self._batch: list[Any] = []
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None
        self._signer: SignerPort | None = None
        self._ticker: asyncio.Task[None] | None = None
        self._sent = 0
        self._failed = 0
        self._missing = 0

    ##### PRIVATE #####

    def _common_client(self) -> tuple[httpx.AsyncClient, SignerPort]:
        match self._client, self._signer:
            case httpx.AsyncClient() as client, SignerPort() as signer:
                return client, signer
            case _:
                msg = f"{type(self).__name__} is not open: the lifespan opens it before the bus delivers"
                raise SinkError(msg)

    async def _enter_tick(self) -> None:
        ### a timer is a loop by nature, alive as long as the driver: a batch never waits longer than `flush`.
        wait = self._conf["flush"].total_seconds()
        while True:
            await asyncio.sleep(wait)
            await self.flush()

    async def _enter_relay(self) -> None:
        ### the relay is a loop by nature: it wakes when an item is stored, or every `poll`, and delivers what is due.
        wait = self._conf["poll"].total_seconds()
        while True:
            with suppress(TimeoutError):
                await asyncio.wait_for(self._nudge.wait(), wait)
            self._nudge.clear()
            await self.flush()

    async def _flush_items(self, items: list[Any]) -> None:
        content, kind = self.body(items)
        match await self._flush_post(content, kind):
            case None:
                self._sent += len(items)
            case Refusal(final=True) if len(items) > 1:
                ### one bad item must not sink its batch: a final refusal is tried again item by item.
                _ = [await self._flush_items([item]) for item in items]
            case refusal:
                self._failed += len(items)
                self.refused(items, refusal)

    async def _flush_post(self, content: bytes, kind: str, attempt: int = 0) -> Refusal | None:
        config = self._conf
        client, signer = self._common_client()
        headers = {
            **{key: secret.get_secret_value() for key, secret in config["headers"].items()},
            **await signer.headers(),
            "Content-Type": kind,
        }
        try:
            reply = await client.request(config["method"], config["endpoint"], content=content, headers=headers)
            status, reason = reply.status_code, f"{reply.status_code} {reply.text[:REASON]}"
        except httpx.TransportError as failure:
            status, reason = 0, f"{type(failure).__name__}: {failure}"
        again = status == 0 or status in RETRIED
        match (status, again):
            case (ok, _) if 200 <= ok < 300:  # noqa: PLR2004 — the 2xx class
                return None
            case (_, True) if attempt < config["retries"]:
                await asyncio.sleep(config["backoff"].total_seconds() * 2**attempt)
                return await self._flush_post(content, kind, attempt + 1)
            case _:
                return Refusal(status=status, reason=f"after {attempt + 1} attempts — {reason}", final=not again)

    async def _flush_relay(self, outbox: OutboxPort) -> None:
        ### a backlog is drained batch after batch: a loop by nature, it ends when a claim comes back short.
        config = self._conf
        while entries := await outbox.claim(config["batch"], config["lease"]):
            await self._relay_deliver(outbox, list(entries))
            if len(entries) < config["batch"]:
                return

    async def _relay_deliver(self, outbox: OutboxPort, entries: list[Entry]) -> None:
        content, kind = self.body([msgspec.Raw(entry.item) for entry in entries])
        match await self._flush_post(content, kind):
            case None:
                _ = [await outbox.ack(entry.key) for entry in entries]
                self._sent += len(entries)
            case Refusal(final=True) if len(entries) > 1:
                _ = [await self._relay_deliver(outbox, [entry]) for entry in entries]
            case Refusal(final=True) as refusal:
                await self._relay_dead(outbox, entries[0], refusal)
            case refusal:
                _ = [await self._relay_release(outbox, entry, refusal) for entry in entries]

    async def _relay_release(self, outbox: OutboxPort, entry: Entry, refusal: Refusal) -> None:
        ### worth another attempt: the next step of the schedule, unless the deadline has passed.
        config = self._conf
        now = datetime.now(UTC)
        schedule = config["schedule"]
        wait = schedule[min(entry.attempts, len(schedule)) - 1]
        match now - entry.created >= config["deadline"]:
            case True:
                late = Refusal(status=refusal.status, reason=f"past its deadline — {refusal.reason}", final=True)
                await self._relay_dead(outbox, entry, late)
            case _:
                await outbox.release(entry.key, now + wait, refusal.reason)

    async def _relay_dead(self, outbox: OutboxPort, entry: Entry, refusal: Refusal) -> None:
        await outbox.dead(entry.key, refusal.reason)
        self._failed += 1
        self.refused([msgspec.Raw(entry.item)], refusal)

    async def _send_store(self, outbox: OutboxPort, view: EventView) -> None:
        ### stored before any network call: the guarantee begins here.
        content = msgspec.json.encode(self.encode(view))
        await outbox.append(self.key(view, content), content)
        self._nudge.set()

    def _send_batch(self, view: EventView) -> bool:
        self._batch.append(self.encode(view))
        return len(self._batch) >= self._conf["batch"]

    def _send_accept(self, view: EventView) -> bool:
        try:
            return self.accept(view)
        except KeyError as missing:
            self._missing += 1
            logger.warning("http refused an event", sink=self.spec.name, missing=str(missing))
            return False

    ############################################################

    ##### HOOKS #####

    def accept(self, view: EventView) -> bool:
        """Whether this event is sent: by default, every kind or the configured ones."""
        kinds = self._conf["kinds"]
        return not kinds or getattr(view, "kind", None) in kinds

    def encode(self, view: EventView) -> Any:
        """What the event becomes in the batch: by default, the view itself."""
        return view

    def body(self, items: Sequence[Any]) -> tuple[bytes, str]:
        """The request body and its content type: by default, the configured encoding."""
        return BODIES[self._conf["encoding"]](items)

    def key(self, view: EventView, content: bytes) -> str:  # noqa: ARG002 — the hook's signature: a subclass reads the view
        """With an outbox, the key an item is stored and deduplicated by: by default, the hash of what it encodes to."""
        return hashlib.sha256(content).hexdigest()

    def refused(self, items: Sequence[Any], refusal: Refusal) -> None:
        """Items the endpoint did not take, and why: by default, a warning with the server's reason."""
        logger.warning(
            "http refused",
            sink=self.spec.name,
            endpoint=self._conf["endpoint"],
            items=len(items),
            status=refusal.status,
            final=refusal.final,
            reason=refusal.reason,
        )

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        config = self._conf
        self._signer = self._given or await AuthSigner(config["auth"]).ready()
        self._client = httpx.AsyncClient(timeout=config["timeout"].total_seconds())
        loop = self._enter_tick() if self._outbox is None else self._enter_relay()
        self._ticker = asyncio.create_task(loop)
        logger.info("http opened", sink=self.spec.name, endpoint=config["endpoint"], batch=config["batch"])
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._ticker:
            case asyncio.Task() as ticker:
                ticker.cancel()
                await asyncio.gather(ticker, return_exceptions=True)
            case _:
                return
        try:
            ### with an outbox, what is left waits stored for the next start; without one, it leaves now.
            _ = self._outbox is None and await self.flush()
        finally:
            client, self._client, self._signer, self._ticker = self._client, None, None, None
            _ = client and await client.aclose()
            logger.info("http closed", sink=self.spec.name, sent=self._sent, failed=self._failed)

    async def health(self) -> bool:
        """Open, its timer alive."""
        return self._ticker is not None and not self._ticker.done()

    async def send(self, view: EventView) -> None:
        """Add the event to the batch — a full batch leaves at once —, or, with an outbox, store it for the relay."""
        self._common_client()
        accepted = self._send_accept(view)
        match self._outbox:
            case None:
                _ = accepted and self._send_batch(view) and await self.flush()
            case outbox:
                _ = accepted and await self._send_store(outbox, view)

    async def flush(self) -> int:
        """Send what is batched now — with an outbox, what is due —; how many events were taken. What is refused goes to
        `refused`, never raised."""
        async with self._lock:
            before = self._sent
            match self._outbox:
                case None:
                    items, self._batch = self._batch, []
                    _ = items and await self._flush_items(items)
                case outbox:
                    await self._flush_relay(outbox)
            return self._sent - before

    async def report(self) -> DeliveryReport:
        """Where this driver's items stand now."""
        held = await self._outbox.report() if self._outbox else {}
        return DeliveryReport(
            sent=self._sent,
            failed=self._failed,
            missing=self._missing,
            pending=held.get(EntryState.PENDING, 0),
            dead=held.get(EntryState.DEAD, 0),
        )

    @property
    def sent(self) -> int:
        """Events delivered so far."""
        return self._sent

    @property
    def failed(self) -> int:
        """Events the endpoint did not take, in the end."""
        return self._failed

    @property
    def missing(self) -> int:
        """Events refused because `accept` read a key they did not carry."""
        return self._missing
