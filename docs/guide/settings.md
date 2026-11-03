# Settings

Every provider reads its settings from the environment (or a `.env` file) on first use, never at import. Pass a
settings object to a provider's constructor to override them in code — tests do.

```python
from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget

otlp = OtlpDriver(OtlpSettings(targets={"phoenix": OtlpTarget(endpoint="http://localhost:6006")}))
```

## All of them

| Variable | Default | Read by | |
|---|---|---|---|
| `ETRACK_BUS_CAPACITY` | `1000` | `AnyioAdapter` | events queued per sink before the newest are dropped |
| `ETRACK_LIVE_BUFFER` | `2000` | `LiveAdapter` | frames kept per thread for a reconnect to replay |
| `ETRACK_LIVE_THREADS` | `256` | `LiveAdapter` | threads kept; the least recently written evicted first |
| `ETRACK_LIVE_BACKLOG` | `1000` | `LiveAdapter` | frames a watcher may lag before it is cut off |
| `ETRACK_OTLP_TARGETS` | `{}` | `OtlpDriver` | backends by name, as JSON: `endpoint`, `headers` (secret) |
| `ETRACK_OTLP_TRACES` | `true` | `OtlpDriver` | send spans |
| `ETRACK_OTLP_LOGS` | `false` | `OtlpDriver` | send a log record per frame |
| `ETRACK_OTLP_TIMEOUT` | `10s` | `OtlpDriver` | per-export deadline |
| `ETRACK_OTLP_FLUSH` | `1s` | `OtlpDriver` | how often a batch leaves |
| `ETRACK_OTLP_SERVICE` | `etrack` | `OtlpDriver` | `service.name` |
| `ETRACK_OTLP_ATTRIBUTES` | `{}` | `OtlpDriver` | extra resource attributes, as JSON |
| `ETRACK_SERVER_HOST` | `127.0.0.1` | `GranianAdapter` | where the viewer listens |
| `ETRACK_SERVER_PORT` | `28130` | `GranianAdapter` | |
| `ETRACK_SERVER_BOOT` | `10s` | `GranianAdapter` | how long opening waits for the socket |

Durations take ISO 8601 (`PT10S`) or seconds (`10`). JSON values are validated on load: a malformed target fails at
startup, not on the first export.

## Errors

Every error e-track raises descends from one root, `etrack.infra.errors.CoreError`:

| Error | Raised when |
|---|---|
| `ChannelError` | an emitted frame is not a valid `RunEvent` (a required field missing or of the wrong type) |
| `BusError` | publishing on a bus that is not open, or a bus whose supervisor died before opening |
| `SinkError` | a sink used before it is open |
| `SourceError` | a config the framework does not take, or a graph the topology adapter cannot read |
| `ServerError` | the viewer's port is taken, or its server does not answer in time |
| `LayoutError` | a topology whose arcs reach nodes it does not declare |
