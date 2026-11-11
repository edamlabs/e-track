"""infra/defaults: the library's composition root — what a provider is not handed, read from `st`.

e-track has no entrypoint: the host's code builds the providers. Each one takes keyword arguments and calls its
function here once, at construction: the arguments given win, the environment fills the rest, and the whole is
validated as the fields are. So `OtlpDriver()` reads `ETRACK_OTLP_*`, and `OtlpDriver(targets=…)` overrides one key."""

from typing import Unpack

from etrack.infra.config.providers import (
    ANYIO,
    GRANIAN,
    HTTP,
    LIVE,
    OTLP,
    PROMETHEUS,
    AnyioConfig,
    GranianConfig,
    HttpConfig,
    LiveConfig,
    OtlpConfig,
    PrometheusConfig,
)
from etrack.infra.settings import settings as st


##### DRIVERS #####
def http(**given: Unpack[HttpConfig]) -> HttpConfig:
    """An `HttpDriver`'s whole configuration: ETRACK_HTTP_*, under what it was handed."""
    read: HttpConfig = {
        "endpoint": st.ETRACK_HTTP_ENDPOINT,
        "method": st.ETRACK_HTTP_METHOD,
        "auth": st.ETRACK_HTTP_AUTH,
        "headers": st.ETRACK_HTTP_HEADERS,
        "encoding": st.ETRACK_HTTP_ENCODING,
        "batch": st.ETRACK_HTTP_BATCH,
        "flush": st.ETRACK_HTTP_FLUSH,
        "timeout": st.ETRACK_HTTP_TIMEOUT,
        "retries": st.ETRACK_HTTP_RETRIES,
        "backoff": st.ETRACK_HTTP_BACKOFF,
        "kinds": st.ETRACK_HTTP_KINDS,
        "schedule": st.ETRACK_HTTP_SCHEDULE,
        "deadline": st.ETRACK_HTTP_DEADLINE,
        "lease": st.ETRACK_HTTP_LEASE,
        "poll": st.ETRACK_HTTP_POLL,
    }
    return HTTP.validate_python(read | given)


def otlp(**given: Unpack[OtlpConfig]) -> OtlpConfig:
    """An `OtlpDriver`'s whole configuration: ETRACK_OTLP_*, under what it was handed."""
    read: OtlpConfig = {
        "targets": st.ETRACK_OTLP_TARGETS,
        "traces": st.ETRACK_OTLP_TRACES,
        "logs": st.ETRACK_OTLP_LOGS,
        "timeout": st.ETRACK_OTLP_TIMEOUT,
        "flush": st.ETRACK_OTLP_FLUSH,
        "service": st.ETRACK_OTLP_SERVICE,
        "attributes": st.ETRACK_OTLP_ATTRIBUTES,
    }
    return OTLP.validate_python(read | given)


##### ADAPTERS #####
def anyio(**given: Unpack[AnyioConfig]) -> AnyioConfig:
    """An `AnyioAdapter`'s whole configuration: ETRACK_BUS_*, under what it was handed."""
    read: AnyioConfig = {"capacity": st.ETRACK_BUS_CAPACITY}
    return ANYIO.validate_python(read | given)


def granian(**given: Unpack[GranianConfig]) -> GranianConfig:
    """A `GranianAdapter`'s whole configuration: ETRACK_SERVER_*, under what it was handed."""
    read: GranianConfig = {"host": st.ETRACK_SERVER_HOST, "port": st.ETRACK_SERVER_PORT, "boot": st.ETRACK_SERVER_BOOT}
    return GRANIAN.validate_python(read | given)


def live(**given: Unpack[LiveConfig]) -> LiveConfig:
    """A `LiveAdapter`'s whole configuration: ETRACK_LIVE_*, under what it was handed."""
    read: LiveConfig = {
        "buffer": st.ETRACK_LIVE_BUFFER,
        "threads": st.ETRACK_LIVE_THREADS,
        "backlog": st.ETRACK_LIVE_BACKLOG,
    }
    return LIVE.validate_python(read | given)


def prometheus(**given: Unpack[PrometheusConfig]) -> PrometheusConfig:
    """A `PrometheusAdapter`'s whole configuration: ETRACK_PROMETHEUS_*, under what it was handed."""
    read: PrometheusConfig = {"namespace": st.ETRACK_PROMETHEUS_NAMESPACE, "buckets": st.ETRACK_PROMETHEUS_BUCKETS}
    return PROMETHEUS.validate_python(read | given)
