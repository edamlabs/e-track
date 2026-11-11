"""infra/config/providers: the providers' knobs — one block per driver and adapter, each field its env variable.

The value types every provider takes beside them: a provider is built with keyword arguments (`OtlpConfig`'s keys,
`HttpConfig`'s…), and what it is not handed `infra/defaults` fills from these fields. `ETRACK_HTTP_*` configures the
HTTP driver read from the environment; a custom driver built on `HttpDriver` passes its own endpoint and auth — one
endpoint per instance, as many instances as systems."""

from datetime import timedelta
from enum import StrEnum, auto
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, SecretStr, TypeAdapter

from etrack.infra.config.auth import Auth, NoAuth
from etrack.infra.config.base import BaseSettings

##### TYPES #####
Port = Annotated[int, Field(ge=1, le=65535)]
Schedule = Annotated[tuple[timedelta, ...], Field(min_length=1)]


class Encoding(StrEnum):
    """How a batch travels: one JSON array, or one JSON object per line (`application/x-ndjson`)."""

    JSON = auto()
    NDJSON = auto()


class OtlpTarget(BaseModel):
    """One collector: its OTLP/HTTP base URL (signals under `/v1/traces`, `/v1/logs`), fixed headers, and how it
    authenticates (`auth`: none, headers, bearer, basic, or google — Cloud Trace through the Telemetry API)."""

    model_config = ConfigDict(frozen=True)

    endpoint: str
    headers: dict[str, SecretStr] = Field(default_factory=dict)
    auth: Auth = Field(default_factory=NoAuth)


##### VALUES #####
class HttpConfig(TypedDict, total=False):
    """An `HttpDriver`'s keyword arguments: where it sends, how it signs, batches and retries, the kinds it sends."""

    endpoint: str
    method: Literal["POST", "PUT"]
    auth: Auth
    headers: dict[str, SecretStr]
    encoding: Encoding
    batch: PositiveInt
    flush: timedelta
    timeout: timedelta
    retries: NonNegativeInt
    backoff: timedelta
    kinds: frozenset[str]
    schedule: Schedule
    deadline: timedelta
    lease: timedelta
    poll: timedelta


class OtlpConfig(TypedDict, total=False):
    """An `OtlpDriver`'s keyword arguments: its collectors, the signals that leave, how fast, under which service."""

    targets: dict[str, OtlpTarget]
    traces: bool
    logs: bool
    timeout: timedelta
    flush: timedelta
    service: str
    attributes: dict[str, str]


class AnyioConfig(TypedDict, total=False):
    """An `AnyioAdapter`'s keyword arguments: events queued per sink."""

    capacity: PositiveInt


class GranianConfig(TypedDict, total=False):
    """A `GranianAdapter`'s keyword arguments: where the viewer listens, how long opening waits."""

    host: str
    port: Port
    boot: timedelta


class LiveConfig(TypedDict, total=False):
    """A `LiveAdapter`'s keyword arguments: frames kept per thread, threads kept, a subscriber's lag."""

    buffer: PositiveInt
    threads: PositiveInt
    backlog: PositiveInt


class PrometheusConfig(TypedDict, total=False):
    """A `PrometheusAdapter`'s keyword arguments: the metrics' prefix and the latency buckets."""

    namespace: str
    buckets: tuple[float, ...]


### each value validated as the fields are: a keyword argument out of range is refused at construction.
HTTP: TypeAdapter[HttpConfig] = TypeAdapter(HttpConfig)
OTLP: TypeAdapter[OtlpConfig] = TypeAdapter(OtlpConfig)
ANYIO: TypeAdapter[AnyioConfig] = TypeAdapter(AnyioConfig)
GRANIAN: TypeAdapter[GranianConfig] = TypeAdapter(GranianConfig)
LIVE: TypeAdapter[LiveConfig] = TypeAdapter(LiveConfig)
PROMETHEUS: TypeAdapter[PrometheusConfig] = TypeAdapter(PrometheusConfig)


##### SETTINGS #####
class ProviderSettings(BaseSettings):
    """The providers' edges: one block per driver and adapter."""

    ##### DRIVERS #####

    ### HTTP
    ### the URL every batch is sent to (empty: nothing leaves); how it signs (JSON: `{"type": "bearer", "token": …}`).
    ETRACK_HTTP_ENDPOINT: str = ""
    ETRACK_HTTP_METHOD: Literal["POST", "PUT"] = "POST"
    ETRACK_HTTP_AUTH: Auth = Field(default_factory=NoAuth)
    ETRACK_HTTP_HEADERS: dict[str, SecretStr] = Field(default_factory=dict)
    ETRACK_HTTP_ENCODING: Encoding = Encoding.NDJSON
    ### events per request at most; the longest an event waits for its batch; per request.
    ETRACK_HTTP_BATCH: PositiveInt = 100
    ETRACK_HTTP_FLUSH: timedelta = timedelta(seconds=1)
    ETRACK_HTTP_TIMEOUT: timedelta = timedelta(seconds=10)
    ### attempts after the first on a network error, 429 or 5xx; the first wait, doubled each retry.
    ETRACK_HTTP_RETRIES: NonNegativeInt = 3
    ETRACK_HTTP_BACKOFF: timedelta = timedelta(milliseconds=500)
    ### kind names (`llm`, `retrieval`…) sent; empty: every kind — config never imports the record.
    ETRACK_HTTP_KINDS: frozenset[str] = frozenset()
    ### with an outbox: the wait before each new attempt (the last repeats), how long an item is tried before it is
    ### dead, how long a claim is held, how often the relay looks for what is due.
    ETRACK_HTTP_SCHEDULE: Schedule = (
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=30),
        timedelta(hours=2),
        timedelta(hours=6),
    )
    ETRACK_HTTP_DEADLINE: timedelta = timedelta(hours=24)
    ETRACK_HTTP_LEASE: timedelta = timedelta(minutes=5)
    ETRACK_HTTP_POLL: timedelta = timedelta(seconds=1)

    ### OTLP
    ### collectors by name as JSON (`{"langfuse": {"endpoint": …, "headers": {…}}}`); none: spans minted, never exported.
    ETRACK_OTLP_TARGETS: dict[str, OtlpTarget] = Field(default_factory=dict)
    ETRACK_OTLP_TRACES: bool = True
    ETRACK_OTLP_LOGS: bool = False
    ### per-export deadline; how often a batch leaves.
    ETRACK_OTLP_TIMEOUT: timedelta = timedelta(seconds=10)
    ETRACK_OTLP_FLUSH: timedelta = timedelta(seconds=1)
    ### `service.name`, and extra resource attributes as JSON.
    ETRACK_OTLP_SERVICE: str = "etrack"
    ETRACK_OTLP_ATTRIBUTES: dict[str, str] = Field(default_factory=dict)

    ##### ADAPTERS #####

    ### ANYIO BUS
    ### events queued per sink; past it, a slow sink loses the newest and the drop is counted.
    ETRACK_BUS_CAPACITY: PositiveInt = 1000

    ### GRANIAN
    ### loopback by default: the frames carry prompts and tool outputs; how long opening waits for the socket.
    ETRACK_SERVER_HOST: str = "127.0.0.1"
    ETRACK_SERVER_PORT: Port = 28130
    ETRACK_SERVER_BOOT: timedelta = timedelta(seconds=10)

    ### LIVE
    ### frames kept per thread for a reconnect; threads kept, least recently written evicted; a subscriber's lag.
    ETRACK_LIVE_BUFFER: PositiveInt = 2000
    ETRACK_LIVE_THREADS: PositiveInt = 256
    ETRACK_LIVE_BACKLOG: PositiveInt = 1000

    ### PROMETHEUS
    ### every metric's prefix; span latency buckets in seconds (JSON list).
    ETRACK_PROMETHEUS_NAMESPACE: str = "etrack"
    ETRACK_PROMETHEUS_BUCKETS: tuple[float, ...] = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
