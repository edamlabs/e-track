"""providers/adapters/sink/prometheus: PrometheusAdapter — every run counted, timed and priced as Prometheus metrics.

Each closed span counts once, by kind, name and outcome, and its latency lands in a histogram; model calls add their
tokens by type and their cost, by model and by the node that made them (a NODE's or a RUN's total is never counted
again); runs in flight are a gauge. Each typed fact (`etrack.models.fact`) counts in a counter of
its own, `fact_<name>`, split by the fields its class marks as labels. The registry is the adapter's own, so two adapters never
collide. Prometheus scrapes `app` — mount it in the host (`/metrics`) or serve it with `GranianAdapter` — and Grafana
reads Prometheus. Names stay bounded: a span's name is its node, tool or model, never a free text."""

from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, Unpack

import msgspec
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, make_asgi_app

from etrack.infra import defaults
from etrack.infra.logger import logger
from etrack.models.event import EventKind, EventPhase, EventView, Failure, ModelRef, Usage
from etrack.models.fact import FACT, LABELS
from etrack.ops.prometheus import prometheus_snake
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from etrack.infra.config.providers import PrometheusConfig
    from etrack.ports.server import Asgi

MS: Final[float] = 1000.0


##### VIEW #####
class PrometheusView(EventView, frozen=True, kw_only=True):
    """What a metric needs of a frame: what it is, how it ended, how long it took, what it spent."""

    kind: EventKind
    phase: EventPhase
    name: str = ""
    node: str = ""
    latency_ms: float | None = None
    model: ModelRef | None = None
    usage: Usage | None = None
    error: Failure | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)
    attributes: dict[str, Any] = msgspec.field(default_factory=dict)


class PrometheusAdapter:
    """Run metrics in an own registry, scraped from `app`."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("prometheus", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = PrometheusView
    phases: ClassVar[frozenset[EventPhase]] = frozenset(
        {EventPhase.START, EventPhase.END, EventPhase.ERROR, EventPhase.INSTANT}
    )

    __slots__ = ("_active", "_conf", "_cost", "_facts", "_latency", "_open", "_registry", "_spans", "_tokens")

    def __init__(self, **given: Unpack[PrometheusConfig]) -> None:
        """Keyword arguments as `PrometheusConfig` names them; what is not given, ETRACK_PROMETHEUS_* fills."""
        config = self._conf = defaults.prometheus(**given)
        self._registry = CollectorRegistry()
        self._open = False
        ns, registry = config["namespace"], self._registry
        self._spans = Counter("spans", "Closed spans", ["kind", "name", "status"], namespace=ns, registry=registry)
        self._latency = Histogram(
            "span_seconds", "Span latency", ["kind", "name"], namespace=ns, registry=registry, buckets=config["buckets"]
        )
        self._active = Gauge("runs_active", "Runs in flight", namespace=ns, registry=registry)
        self._tokens = Counter("tokens", "Model tokens", ["model", "node", "type"], namespace=ns, registry=registry)
        self._cost = Counter("cost_usd", "Model cost in US dollars", ["model", "node"], namespace=ns, registry=registry)
        self._facts: dict[str, Counter] = {}

    ##### PRIVATE #####

    def _send_spent(self, view: PrometheusView) -> None:
        ### model calls only: a NODE's or a RUN's usage is the total of calls already counted.
        match (view.kind, view.usage):
            case (EventKind.LLM, Usage() as usage):
                model = (view.model or ModelRef()).name or view.name
                spent = {
                    "input": usage.input_tokens,
                    "output": usage.output_tokens,
                    "cache_read": usage.cache_read_tokens,
                    "cache_write": usage.cache_write_tokens,
                    "reasoning": usage.reasoning_tokens,
                }
                _ = [self._tokens.labels(model, view.node, kind).inc(count) for kind, count in spent.items() if count]
                _ = usage.cost_usd and self._cost.labels(model, view.node).inc(usage.cost_usd)
            case _:
                pass

    def _send_closed(self, view: PrometheusView) -> None:
        failed = view.phase is EventPhase.ERROR or view.error is not None
        self._spans.labels(view.kind, view.name, "error" if failed else "ok").inc()
        _ = view.latency_ms is not None and self._latency.labels(view.kind, view.name).observe(view.latency_ms / MS)
        self._send_spent(view)
        _ = view.kind is EventKind.RUN and self._active.dec()

    def _send_fact(self, view: PrometheusView) -> None:
        match view.attributes.get(FACT):
            case str() as name:
                labels = tuple(view.attributes[LABELS])
                counter = self._facts.get(name) or self._send_counter(name, labels)
                values = [str(view.payload[label]) for label in labels]
                _ = counter.labels(*values).inc() if labels else counter.inc()
            case _:
                pass

    def _send_counter(self, name: str, labels: tuple[str, ...]) -> Counter:
        ### one counter per fact, made the first time it is seen: its labels are its class's, fixed for good.
        counter = Counter(
            f"fact_{prometheus_snake(name)}",
            f"Facts {name}",
            labels,
            namespace=self._conf["namespace"],
            registry=self._registry,
        )
        self._facts[name] = counter
        return counter

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._open = True
        logger.info("prometheus opened", namespace=self._conf["namespace"])
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._open = False
        logger.info("prometheus closed")

    async def health(self) -> bool:
        """Open: its metrics are being kept."""
        return self._open

    async def send(self, view: EventView) -> None:
        """A run's start counts it in flight; every close counts, times and prices the span; a fact counts itself."""
        frame = PrometheusView.project(view)
        match frame.phase:
            case EventPhase.START:
                _ = frame.kind is EventKind.RUN and self._active.inc()
            case EventPhase.INSTANT:
                self._send_fact(frame)
            case _:
                self._send_closed(frame)

    @property
    def registry(self) -> CollectorRegistry:
        """The adapter's own registry: what `app` exposes, what a test or a push reads."""
        return self._registry

    @property
    def app(self) -> Asgi:
        """The ASGI app Prometheus scrapes — mount it at `/metrics`."""
        return make_asgi_app(registry=self._registry)
