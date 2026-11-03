# Sinks

A sink is anything that takes events: the OTLP driver, the live buffer, your own code. The bus between the channel
and the sinks gives each one its own bounded queue and its own worker, so the run never waits for a sink and no sink
waits for another.

```python
from etrack.providers.adapters.bus.anyio import AnyioAdapter

bus = AnyioAdapter()
bus.subscribe(live)
bus.subscribe(otlp, select=lambda event: None if event.part == "reasoning" else event)   # a policy per sink
async with bus:                     # open it last: it is closed first, and delivers what is queued before closing
    ...
print(bus.dropped, bus.failed)      # {} {} — what each sink lost (queue full) and refused (raised)
```

## `AnyioAdapter`

| | |
|---|---|
| `subscribe(sink, select=None)` | serve a sink from now on — before or after the bus opens; `select` sees each event first and returns it, a transformed copy, or `None` to skip it, on the sink's own worker |
| `publish(event)` | returns at once, from any thread; the channel calls it, you normally don't |
| `dropped`, `failed` | events lost per sink because its queue was full; deliveries that raised |

Setting: `ETRACK_BUS_CAPACITY` (1000) — events queued per sink. Past it, a slow sink loses the newest and the loss is
counted, never the run's problem. A synchronous burst longer than the capacity, with no `await` in between, drops the
rest: give the loop a turn in long synchronous loops.

## What a sink declares

Three class attributes and one method, plus the lifecycle every provider has:

```python
from typing import ClassVar

from etrack.models.event import EventPhase, EventView
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload


class CostSink:
    """Every LLM call's tokens, summed per run."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("cost", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = Cost                          # the fields it reads (→ The record · Views)
    phases: ClassVar[frozenset[EventPhase]] = frozenset({EventPhase.END})   # the phases it wants: no deltas, ever

    def __init__(self) -> None:
        self.tokens: dict[str, int] = {}

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): ...
    async def health(self) -> bool: return True

    async def send(self, view: Cost) -> None:
        if view.kind == "llm" and view.usage:
            self.tokens[view.run_id] = self.tokens.get(view.run_id, 0) + view.usage.total_tokens
```

| Declares | Effect |
|---|---|
| `spec` | its name in `bus.dropped` / `bus.failed` and in the logs |
| `view` | the bus narrows each event onto it before `send` |
| `phases` | the bus skips the other phases before queueing: a sink that ignores token deltas never pays for them |
| `send` | the one delivery call; raising is counted in `bus.failed` and logged, the next event still arrives |

## `LiveAdapter` — the live buffer

Keeps the last frames of every conversation in memory and pushes new ones to whoever watches: what the viewer, a chat
UI or a reconnecting client read.

```python
from etrack.providers.adapters.sink.live import LiveAdapter

async with LiveAdapter() as live:
    bus.subscribe(live)
    ...
    async for frame in live.watch("t1", after=41):     # frames 42… kept, then every new one, live
        print(frame.offset, frame.event.kind, frame.event.name)
    live.threads()                                       # the kept conversations, newest first
```

| | |
|---|---|
| `watch(thread, after=-1)` | replay what is kept past `after`, then follow; a client that reconnects with the last offset it saw misses nothing still kept |
| `threads()` | every kept thread: next offset, its runs, its last frame's time — newest first |
| `offset(thread)` | how many frames the thread has had |

`offset` is per thread and contiguous across runs, unlike `seq`, which restarts each run.

| setting | default | |
|---|---|---|
| `ETRACK_LIVE_BUFFER` | `2000` | frames kept per thread for a reconnect to replay |
| `ETRACK_LIVE_THREADS` | `256` | threads kept; the least recently written is evicted first |
| `ETRACK_LIVE_BACKLOG` | `1000` | frames a watcher may lag before it is cut off, rather than slow the bus |

## `OtlpDriver`

The sink that speaks OpenTelemetry — its own page: [Backends](backends.md).
