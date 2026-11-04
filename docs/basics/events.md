# Send events

Events go where sinks take them. Subscribe each sink to the bus once; every sink gets every event, on its own worker
— a slow or failing one never holds up the run or the others.

```python
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver

# open the sinks first
async with LiveAdapter() as live, OtlpDriver() as otlp:
    bus = AnyioAdapter()
    # in memory: the viewer, a chat, a reconnect
    bus.subscribe(live)
    # out: Langfuse, Phoenix, LangSmith, Tempo…
    bus.subscribe(otlp)
    # open the bus last: closing it delivers what is queued
    async with bus:
        ...
    # {} {} — nothing lost, nothing refused
    print(bus.dropped, bus.failed)
```

## The sinks that ship

| Sink | Sends to | Read more |
|---|---|---|
| `LiveAdapter` | memory: the last frames of every conversation, replayed and pushed live | [The viewer](viewer.md) |
| `OtlpDriver` | any OpenTelemetry backend, over OTLP/HTTP: spans, and log records if you want | [Langfuse](../integrations/langfuse.md) · [Phoenix](../integrations/phoenix.md) · [LangSmith](../integrations/langsmith.md) · [OpenTelemetry](../integrations/opentelemetry.md) |
| yours | anything | [Custom sinks](../advanced/sinks.md) |

## Where the OTLP driver sends

From the environment — no code change between environments:

```bash
ETRACK_OTLP_TARGETS='{"phoenix": {"endpoint": "http://localhost:6006"}}'
```

Several targets receive everything at once. No target: nothing leaves. Every setting → [Settings](../advanced/settings.md).

## Order matters, once

Open the sinks before the bus, the bus last. Leaving the bus closes every queue and lets each sink take what was
still waiting; then the sinks close — the OTLP driver flushes its last batch. Inside a FastAPI or Litestar lifespan,
the same order on one `AsyncExitStack`.
