# Upgrading to 0.6

0.6 is a pre-1.0 minor: it breaks, each break small and named here.

## From 0.5

| What | 0.5 | 0.6 |
|---|---|---|
| Overriding a provider's settings in code | `OtlpDriver(OtlpSettings(targets=…))`, `HttpDriver(HttpSettings(…))` | keyword arguments: `OtlpDriver(targets=…)`, `HttpDriver(endpoint=…, batch=1)` |
| Settings classes | `etrack.infra.config.providers.drivers.sink.otlp.OtlpSettings`, `….http.HttpSettings`… | gone; `OtlpTarget`, `Encoding` from `etrack.infra.config.providers` |
| When the environment is read | at a provider's first use | at e-track's first import: set `ETRACK_*` before it |
| A refused HTTP batch | dropped and raised from `flush` | final refusals retried item by item; what is refused in the end goes to `refused(items, refusal)`, never raised — drop a `flush` override that swallowed `SinkError` |
| A custom signer | overwrite `_signer` after `__aenter__` | `HttpDriver(signer=…)`, any object with `async headers()` |
| `visit` | counted by node name across the run | counted per mount: one subgraph mounted twice counts its nodes apart |
| A node's END payload | `{"keys": […]}`, empty for a `Command` | `{"keys": […]}`, and `goto` when it returned `Command`s |
| `usage` on NODE and RUN END | absent | the total of the model calls under it — sum model calls only |
| Prometheus | `tokens_total{model,type}`, `cost_usd_total{model}`; facts not counted | `tokens_total{model,node,type}`, `cost_usd_total{model,node}`; `phases` gains `instant` and facts count |
| A custom bus | `subscribe(sink, select=None)` | `subscribe(sink, select=None, *, redact=None, delivery=Delivery.BEST_EFFORT)` |
| `Redact` | `etrack.processors.fold.Redact` | `etrack.models.event.Redact` |

## New, nothing to change

The run reached from inside it (`etrack.logic.handle.run`: `span`, `declare`, `annotate`, `fact`) → [The run from
inside](runs.md); a mask per subscription; `RunView` and a gate that fails closed, guaranteed delivery through an outbox
→ [Custom drivers](drivers.md); cost per node and per run with your `Pricer`.
