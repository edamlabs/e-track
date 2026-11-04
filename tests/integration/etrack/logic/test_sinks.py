"""tests/integration/etrack/logic/sinks: a deep agent's run through the bus into the HTTP driver and into Prometheus.

The HTTP driver posts to a real local endpoint; Prometheus is scraped over a real port, served by granian, and its
exposition parsed the way Prometheus parses it. No sandbox: every collaborator runs in the process."""

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import structlog
from prometheus_client.parser import text_string_to_metric_families

from etrack.infra.config.auth import BearerAuth
from etrack.infra.config.base import Secret
from etrack.infra.config.providers.adapters.server.granian import GranianSettings
from etrack.infra.config.providers.drivers.sink.http import HttpSettings
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.prometheus import PrometheusAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.http import HttpDriver
from support.endpoint import fake_endpoint
from support.port import free_port

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_httpserver import HTTPServer

pytestmark = pytest.mark.integration


async def test_sinks_run_reaches_http_and_prometheus(
    deep_agent: Callable[[], Any], httpserver: HTTPServer, wait: float
) -> None:
    endpoint = fake_endpoint(httpserver)
    config = HttpSettings(
        endpoint=endpoint.url, auth=BearerAuth(token=Secret("t")), batch=5, flush=timedelta(milliseconds=50)
    )
    async with HttpDriver(config) as http, PrometheusAdapter() as metrics:
        bus = AnyioAdapter()
        bus.subscribe(http)
        bus.subscribe(metrics)
        async with bus:
            tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
            with structlog.contextvars.bound_contextvars(tenant="acme"), tracker.track("sinks", {}) as tracked:
                await deep_agent().ainvoke({"messages": [("user", "¿qué es una póliza?")]}, tracked.config)
        async with (
            GranianAdapter(metrics.app, GranianSettings(port=free_port())) as server,
            httpx.AsyncClient(base_url=server.url, timeout=wait) as client,
        ):
            scraped = (await client.get("/")).text
    posted = [json.loads(line) for body in endpoint.bodies for line in body.splitlines()]
    ### every frame but the token deltas left, in order, signed, in batches of five at most.
    assert [event["seq"] for event in posted] == sorted(event["seq"] for event in posted)
    assert {event["kind"] for event in posted} >= {"run", "node", "llm", "subagent", "mcp"}
    assert all(len(body.splitlines()) <= 5 for body in endpoint.bodies)
    assert {headers["Authorization"] for headers in endpoint.headers} == {"Bearer t"}
    ### a key bound around the run rides every frame to every sink, as structlog carries it to every line.
    assert {event["attributes"].get("tenant") for event in posted} == {"acme"}
    samples = {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(scraped)
        for sample in family.samples
    }
    assert samples[("etrack_runs_active", ())] == 0
    assert samples[("etrack_spans_total", (("kind", "mcp"), ("name", "onto_query"), ("status", "ok")))] == 1
    assert samples[("etrack_spans_total", (("kind", "run"), ("name", "LangGraph"), ("status", "ok")))] == 1
