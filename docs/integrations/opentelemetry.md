# OpenTelemetry

`OtlpDriver` turns every run into OpenTelemetry spans — and log records if you want them — and exports them over
OTLP/HTTP to every target at once: any collector, Grafana Tempo, Jaeger, and the LLM backends that speak OTLP
([Langfuse](langfuse.md), [Phoenix](phoenix.md), [LangSmith](langsmith.md)). Install `e-track[otel]`.

```python
from etrack.providers.drivers.sink.otlp import OtlpDriver

# targets from ETRACK_OTLP_TARGETS; closing flushes the last batch
async with OtlpDriver() as otlp:
    bus.subscribe(otlp)
```

```bash
ETRACK_OTLP_TARGETS='{"collector": {"endpoint": "http://localhost:4318"}}'
```

The endpoint is the OTLP/HTTP base URL: spans go to `/v1/traces`, logs to `/v1/logs` under it. Headers authenticate
(`"headers": {...}`) and are kept secret in every repr and log. Several targets receive everything; none, nothing
leaves.

A `start` opens a span and its `end` or `error` closes it at the event's own time; an `instant` is a span born
closed. Token deltas never reach the driver.

## One span, three dialects

Each backend reads different attribute names. Every span carries all three, so each finds what it knows:

| Dialect | Read by | Keys |
|---|---|---|
| OpenTelemetry GenAI | Tempo, Grafana, Datadog, any GenAI-aware backend | `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.usage.*`, `gen_ai.tool.name`, `gen_ai.conversation.id` |
| OpenInference | Phoenix, Arize | `openinference.span.kind`, `input.value`, `output.value`, `llm.model_name`, `llm.token_count.*`, `session.id` |
| Langfuse | Langfuse | `langfuse.observation.type`, `langfuse.session.id`, `langfuse.observation.usage_details` |

Plus e-track's own: `etrack.run_id`, `etrack.thread_id`, `etrack.kind`, `etrack.node`, `etrack.step`, `etrack.visit`
— and every `attributes` entry of the frame (your `app.*` facts included).

**Ids are derived, never minted.** The trace id is the run id; a span id is the low 64 bits of the frame's id. The same
run and the same span carry the same ids in every backend, in the viewer and in your logs: search one trace id
anywhere.

**Usage is priced right.** Langfuse gets usage as exclusive buckets — `input` and `output` without their cached and
reasoning parts, plus `input_cache_read`, `input_cache_creation`, `output_reasoning` — so cached input is not billed at
the full input rate.

## Logs

```bash
ETRACK_OTLP_LOGS=true
```

Every frame is also an OpenTelemetry log record on its span — severity by phase, `event_name` `etrack.<kind>.<phase>`.
And your own application logs can travel with them: `otlp.processor()` is a structlog processor that turns every line
of your logger into a log record too.

```python
structlog.configure(processors=[..., otlp.processor(), structlog.dev.ConsoleRenderer()])
```

## Settings

| setting | default | |
|---|---|---|
| `ETRACK_OTLP_TARGETS` | `{}` | backends by name: `endpoint`, `headers` |
| `ETRACK_OTLP_TRACES` | `true` | send spans |
| `ETRACK_OTLP_LOGS` | `false` | send a log record per frame |
| `ETRACK_OTLP_TIMEOUT` | `10s` | per-export deadline |
| `ETRACK_OTLP_FLUSH` | `1s` | how often a batch leaves |
| `ETRACK_OTLP_SERVICE` | `etrack` | `service.name` |
| `ETRACK_OTLP_ATTRIBUTES` | `{}` | extra resource attributes |

The driver owns a private `TracerProvider` and `LoggerProvider`: it never touches the process-global OpenTelemetry
setup, so it lives beside any instrumentation you already have. `await otlp.flush()` exports everything buffered now.

## What is verified

| Backend | Status |
|---|---|
| OpenTelemetry Collector | tested on every change: span tree and log records, read back by trace id |
| Phoenix 21 | tested on every change: the OpenInference kinds as Phoenix reads them |
| Langfuse | measured against its native handler in deeptrack's tracing A/B: nesting, generations, tokens, cost |
| LangSmith | keys emitted, not verified against LangSmith yet |
