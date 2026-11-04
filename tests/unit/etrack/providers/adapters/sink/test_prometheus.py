"""tests/unit/etrack/providers/adapters/sink/prometheus: spans counted, timed and priced; runs in flight; the scrape app."""

import httpx

from etrack.infra.config.providers.adapters.sink.prometheus import PrometheusSettings
from etrack.models.event import EventKind, EventPhase, Failure, ModelRef, Usage
from etrack.ports.sink import SinkPort
from etrack.providers.adapters.sink.prometheus import PrometheusAdapter, PrometheusView
from unit.etrack.conftest import frame


async def test_prometheus_meets_port() -> None:
    assert isinstance(PrometheusAdapter(), SinkPort)


async def test_prometheus_counts_times_and_prices() -> None:
    async with PrometheusAdapter(PrometheusSettings(namespace="t")) as metrics:
        assert await metrics.health()
        sent = [
            frame(0, EventPhase.START, kind=EventKind.RUN, name="agent"),
            frame(
                1,
                EventPhase.END,
                kind=EventKind.LLM,
                name="gemini",
                latency_ms=1200.0,
                model=ModelRef(name="gemini-2.5-flash"),
                usage=Usage(input_tokens=10, output_tokens=4, cache_read_tokens=2, cost_usd=0.5),
            ),
            frame(2, EventPhase.ERROR, kind=EventKind.TOOL, name="search", error=Failure(type="Timeout")),
            frame(3, EventPhase.START, kind=EventKind.NODE, name="plan"),
        ]
        _ = [await metrics.send(PrometheusView.project(event)) for event in sent]
        value = metrics.registry.get_sample_value
        assert value("t_runs_active") == 1
        assert value("t_spans_total", {"kind": "llm", "name": "gemini", "status": "ok"}) == 1
        assert value("t_spans_total", {"kind": "tool", "name": "search", "status": "error"}) == 1
        assert value("t_span_seconds_count", {"kind": "llm", "name": "gemini"}) == 1
        assert value("t_tokens_total", {"model": "gemini-2.5-flash", "type": "input"}) == 10
        assert value("t_tokens_total", {"model": "gemini-2.5-flash", "type": "reasoning"}) is None
        assert value("t_cost_usd_total", {"model": "gemini-2.5-flash"}) == 0.5
        await metrics.send(PrometheusView.project(frame(4, EventPhase.END, kind=EventKind.RUN, name="agent")))
        assert value("t_runs_active") == 0
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=metrics.app), base_url="http://m") as client:
            scraped = (await client.get("/")).text
    assert 't_spans_total{kind="llm",name="gemini",status="ok"} 1.0' in scraped
    assert not await metrics.health()
