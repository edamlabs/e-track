# Logging

e-track never configures logging. It writes to one structlog logger, named `etrack`, and your setup decides what is
rendered, where, and at which level.

## Every event, one line on your logger

The channel forwards each event as a line, at a level picked by its phase:

| `phase` | level |
|---|---|
| `start`, `end`, `instant` | `INFO` |
| `delta` | `DEBUG` |
| `error` | `ERROR` |

```
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb707239aa803e77c8636a01 kind=node latency_ms=0.754 name=plan node=plan parent=01a1a242cb6e773194d01db435461601 phase=end run_id=01a1a242cb6e773194d01db435461601 seq=2 step=1 thread_id=t1
```

The line carries the coordinates and the measures — never the payload: a log is read by people and grepped by
machines. Empty fields are left out.

| `EventChannel(...)` kwarg | default | |
|---|---|---|
| `forward` | `LogView` | the view each line is narrowed onto; any `EventView` subclass picks other fields; `None` turns forwarding off |
| `model` | `RunEvent` | the record every frame is validated into — a subclass of yours grows it |

The channel is a logger of its own, separate from yours: your level filter never drops an event before it reaches the
sinks. Only the forwarded line obeys your level.

## e-track's own lines

On the same `etrack` logger: `bus opened` / `bus closed` (with `dropped` and `failed` per sink), `otlp opened` /
`otlp closed`, `live opened`, `server opened url=…`, and `bus delivery failed` when a sink raises. Route or silence
the `etrack` logger like any other.

## Inside a run

Within `tracker.track(...)`, structlog's contextvars carry `run_id` and `thread_id`: if your chain includes
`structlog.contextvars.merge_contextvars`, every line your own code logs during the run is tagged with it — and its
`run_id` is the trace id in every backend.

## Your logs to OpenTelemetry

With the OTLP driver, `otlp.processor()` is a structlog processor that also sends every line of your logger as an
OpenTelemetry log record, beside the spans. → [OpenTelemetry](../integrations/opentelemetry.md)
