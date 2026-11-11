"""providers/drivers/sink/http: HttpDriver — events batched to any HTTP endpoint; the base a custom driver is built on.

The bus already gives every sink its own worker, a bounded queue and a `select`: this driver adds what a remote system
needs. Events gather in a batch that leaves when it is full or when the oldest has waited `flush`; a request that
meets a network error, a 429 or a 5xx is retried with a doubling backoff, any other refusal is not; every request is
signed by the configured `Auth`. Leaving the driver sends what is left.

A custom driver subclasses it and overrides what it must, nothing else:

- `view` — the fields it reads (the bus narrows every event onto it before `send`);
- `phases` — the phases it wants (the bus skips the rest before queueing);
- `accept(view)` — whether this event is sent at all — the project's gate: it fails closed, an `accept` that reads a
  key the event does not carry (`view.attributes["app.owner"]`) refuses the event and counts it (`missing`), so a
  missing fact never passes as a default;
- `encode(view)` — the item the event becomes (a `msgspec.Struct`, a dict, anything msgspec encodes);
- `body(items)` — the request body and its content type, when the endpoint wants a shape of its own."""

import asyncio
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
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from etrack.infra.config.providers import HttpConfig

PHASES: Final[frozenset[EventPhase]] = frozenset(
    {EventPhase.START, EventPhase.END, EventPhase.ERROR, EventPhase.INSTANT}
)
### the refusals worth another attempt: too many requests, and the server's own failures.
RETRIED: Final[frozenset[int]] = frozenset({408, 425, 429, 500, 502, 503, 504})


def body_json(items: Sequence[Any]) -> tuple[bytes, str]:
    """A batch as one JSON array."""
    return msgspec.json.encode(items), "application/json"


def body_ndjson(items: Sequence[Any]) -> tuple[bytes, str]:
    """A batch as one JSON value per line."""
    return b"".join(msgspec.json.encode(item) + b"\n" for item in items), "application/x-ndjson"


BODIES: Final[Mapping[Encoding, Callable[[Sequence[Any]], tuple[bytes, str]]]] = MappingProxyType(
    {Encoding.JSON: body_json, Encoding.NDJSON: body_ndjson}
)


class HttpDriver:
    """A batching, retrying, signed HTTP sink — use it as it is, or subclass it for a system of your own."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("http", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True)
    view: ClassVar[type[EventView]] = RunEvent
    phases: ClassVar[frozenset[EventPhase]] = PHASES

    __slots__ = ("_batch", "_client", "_conf", "_failed", "_lock", "_missing", "_sent", "_signer", "_ticker")

    def __init__(self, **given: Unpack[HttpConfig]) -> None:
        """Keyword arguments as `HttpConfig` names them; what is not given, ETRACK_HTTP_* fills (`infra/defaults`)."""
        self._conf = defaults.http(**given)
        self._batch: list[Any] = []
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None
        self._signer: AuthSigner | None = None
        self._ticker: asyncio.Task[None] | None = None
        self._sent = 0
        self._failed = 0
        self._missing = 0

    ##### PRIVATE #####

    def _common_client(self) -> tuple[httpx.AsyncClient, AuthSigner]:
        match self._client, self._signer:
            case httpx.AsyncClient() as client, AuthSigner() as signer:
                return client, signer
            case _:
                msg = f"{type(self).__name__} is not open: the lifespan opens it before the bus delivers"
                raise SinkError(msg)

    async def _enter_tick(self) -> None:
        ### a timer is a loop by nature, alive as long as the driver: a batch never waits longer than `flush`.
        wait = self._conf["flush"].total_seconds()
        while True:
            await asyncio.sleep(wait)
            try:
                await self.flush()
            except SinkError as failure:
                logger.warning("http flush failed", sink=self.spec.name, error=failure.message)

    async def _flush_post(self, content: bytes, kind: str, attempt: int = 0) -> None:
        config = self._conf
        client, signer = self._common_client()
        headers = {
            **{key: secret.get_secret_value() for key, secret in config["headers"].items()},
            **await signer.headers(),
            "Content-Type": kind,
        }
        try:
            reply = await client.request(config["method"], config["endpoint"], content=content, headers=headers)
            status, reason = reply.status_code, f"{reply.status_code} {reply.text[:200]}"
        except httpx.TransportError as failure:
            status, reason = 0, f"{type(failure).__name__}: {failure}"
        match status:
            case ok if 200 <= ok < 300:  # noqa: PLR2004 — the 2xx class
                return
            case again if (again == 0 or again in RETRIED) and attempt < config["retries"]:
                await asyncio.sleep(config["backoff"].total_seconds() * 2**attempt)
                await self._flush_post(content, kind, attempt + 1)
            case _:
                msg = (
                    f"{self.spec.name}: {config['endpoint']} refused the batch after {attempt + 1} attempts — {reason}"
                )
                raise SinkError(msg)

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

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        config = self._conf
        self._signer = await AuthSigner(config["auth"]).ready()
        self._client = httpx.AsyncClient(timeout=config["timeout"].total_seconds())
        self._ticker = asyncio.create_task(self._enter_tick())
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
            await self.flush()
        finally:
            client, self._client, self._signer, self._ticker = self._client, None, None, None
            _ = client and await client.aclose()
            logger.info("http closed", sink=self.spec.name, sent=self._sent, failed=self._failed)

    async def health(self) -> bool:
        """Open, its timer alive."""
        return self._ticker is not None and not self._ticker.done()

    async def send(self, view: EventView) -> None:
        """Add the event to the batch; a full batch leaves at once."""
        self._common_client()
        _ = self._send_accept(view) and self._batch.append(self.encode(view))
        _ = len(self._batch) >= self._conf["batch"] and await self.flush()

    async def flush(self) -> int:
        """Send what is batched now; how many events left. A refusal drops the batch and raises."""
        async with self._lock:
            items, self._batch = self._batch, []
            match items:
                case []:
                    return 0
                case _:
                    content, kind = self.body(items)
                    try:
                        await self._flush_post(content, kind)
                    except SinkError:
                        self._failed += len(items)
                        raise
                    self._sent += len(items)
                    return len(items)

    @property
    def sent(self) -> int:
        """Events delivered so far."""
        return self._sent

    @property
    def failed(self) -> int:
        """Events dropped with a refused batch."""
        return self._failed

    @property
    def missing(self) -> int:
        """Events refused because `accept` read a key they did not carry."""
        return self._missing
