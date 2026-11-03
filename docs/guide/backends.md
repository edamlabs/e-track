# Backends

`OtlpDriver` turns frames into OpenTelemetry spans — and, if you want, log records — and exports them over
OTLP/HTTP to every target you configure, at once. A `start` opens a span, its `end` or `error` closes it at the frame's
own time; an `instant` is a span born closed. Token deltas never reach it.

```python
from etrack.providers.drivers.sink.otlp import OtlpDriver

async with OtlpDriver() as otlp:        # targets from ETRACK_OTLP_TARGETS; closing flushes the last batch
    bus.subscribe(otlp)
```

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

## Targets

`ETRACK_OTLP_TARGETS` is a JSON object: one entry per backend, its OTLP/HTTP base URL (signals go to `/v1/traces` and
`/v1/logs` under it) and the headers it authenticates with. The headers are secrets: masked in every repr and log.

=== "Langfuse"

    ```bash
    ETRACK_OTLP_TARGETS='{"langfuse": {
      "endpoint": "https://cloud.langfuse.com/api/public/otel",
      "headers": {"Authorization": "Basic <base64 of public_key:secret_key>"}}}'
    ```

    Self-hosted: `http://<host>:3000/api/public/otel`. Sessions are threads; observation types follow the span kind
    (`generation`, `tool`, `agent`, `retriever`, `chain`).

=== "Phoenix"

    ```bash
    ETRACK_OTLP_TARGETS='{"phoenix": {"endpoint": "http://localhost:6006"}}'
    ETRACK_OTLP_ATTRIBUTES='{"openinference.project.name": "my-agent"}'
    ```

    Phoenix 21 authenticates OTLP by default: send its API key as a header, or run it with
    `PHOENIX_ENABLE_AUTH=false` locally. The project comes from the `openinference.project.name` resource attribute.

=== "LangSmith"

    ```bash
    ETRACK_OTLP_TARGETS='{"langsmith": {
      "endpoint": "https://api.smith.langchain.com/otel",
      "headers": {"x-api-key": "<key>", "Langsmith-Project": "my-agent"}}}'
    ```

=== "Collector · Tempo · Jaeger"

    ```bash
    ETRACK_OTLP_TARGETS='{"collector": {"endpoint": "http://localhost:4318"}}'
    ```

    Any OpenTelemetry Collector, Grafana Tempo or Jaeger with its OTLP/HTTP receiver on.

Several at once:

```bash
ETRACK_OTLP_TARGETS='{"langfuse": {...}, "phoenix": {...}}'
```

No target set: spans are still minted and dropped — nothing leaves.

## What is verified

| Backend | Status |
|---|---|
| OpenTelemetry Collector | tested on every change: the span tree and the log records, read back by trace id (integration tier) |
| Phoenix 21 | tested on every change: the OpenInference kinds as Phoenix reads them — `AGENT` for a subagent, `TOOL`, `LLM` (integration tier) |
| Langfuse | measured in deeptrack's tracing A/B against the native handler: nesting, generations, tokens, cost |
| LangSmith | the keys are emitted; not verified against LangSmith yet — check its OpenTelemetry docs for the current endpoint |

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
