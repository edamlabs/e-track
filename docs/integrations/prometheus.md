# Prometheus and Grafana

Two ways into Grafana: **metrics** — counts, latencies, tokens and cost, scraped by Prometheus from the
`PrometheusAdapter` — and **traces** — every span, sent over OTLP to Tempo or Grafana Cloud.

## Metrics

Install `e-track[prometheus]`.

```python
from etrack.providers.adapters.sink.prometheus import PrometheusAdapter

async with PrometheusAdapter() as metrics:
    bus.subscribe(metrics)
    # mount the scrape app in your web app…
    app.mount("/metrics", metrics.app)
    # …or serve it on its own port
    async with GranianAdapter(metrics.app) as server:
        ...
```

| Metric | Labels | |
|---|---|---|
| `etrack_spans_total` | `kind`, `name`, `status` (`ok`, `error`) | every closed span |
| `etrack_span_seconds` | `kind`, `name` | span latency, a histogram |
| `etrack_runs_active` | | runs in flight |
| `etrack_tokens_total` | `model`, `node`, `type` (`input`, `output`, `cache_read`, `cache_write`, `reasoning`) | model tokens, from model calls only |
| `etrack_cost_usd_total` | `model`, `node` | model cost, when the source or your `Pricer` knows it |
| `etrack_fact_<name>_total` | the fact's `labels` | one counter per typed fact → [The run from inside](../advanced/runs.md) |

A span's `name` is its node, tool, subagent or model — bounded by your graph and your tools, never free text.

| Setting | default | |
|---|---|---|
| `ETRACK_PROMETHEUS_NAMESPACE` | `etrack` | every metric's prefix |
| `ETRACK_PROMETHEUS_BUCKETS` | `[0.01 … 60]` | latency buckets, in seconds |

```yaml
# prometheus.yml
scrape_configs:
  - job_name: agents
    static_configs: [{targets: ["127.0.0.1:8000"]}]
    metrics_path: /metrics
```

Queries to start from: calls per second by tool `sum by (name) (rate(etrack_spans_total{kind="tool"}[5m]))`; p95 model
latency `histogram_quantile(0.95, sum by (le, name) (rate(etrack_span_seconds_bucket{kind="llm"}[5m])))`; spend per
hour `sum by (model) (increase(etrack_cost_usd_total[1h]))`; error ratio `sum(rate(etrack_spans_total{status="error"}[5m])) / sum(rate(etrack_spans_total[5m]))`.

The registry is the adapter's own: two adapters never collide, and your app's metrics stay in yours.

## Traces

Tempo and Grafana Cloud ingest OTLP: the OTLP driver with a basic auth.

```bash
ETRACK_OTLP_TARGETS='{"grafana": {
  "endpoint": "https://otlp-gateway-prod-eu-west-2.grafana.net/otlp",
  "auth": {"type": "basic", "username": "<instance id>", "password": "<token>"}}}'
```

Self-hosted Tempo: `http://<host>:4318`, no auth. → [OpenTelemetry](opentelemetry.md) · [Authentication](../advanced/auth.md)
