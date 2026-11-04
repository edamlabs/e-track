# Custom sinks and policies

A sink is any class with three declarations and one method. The bus narrows each event to what the sink reads, skips
the phases it does not want before queueing, and delivers on the sink's own worker.

## The bus: policies and losses

| | |
|---|---|
| `subscribe(sink, select=None)` | serve a sink from now on — before or after the bus opens; `select` sees each event first and returns it, a transformed copy, or `None` to skip it, on the sink's own worker |
| `publish(event)` | returns at once, from any thread; the channel calls it, you normally don't |
| `dropped`, `failed` | events lost per sink because its queue was full; deliveries that raised |

Setting: `ETRACK_BUS_CAPACITY` (1000) — events queued per sink. Past it, a slow sink loses the newest and the loss is
counted, never the run's problem. A synchronous burst longer than the capacity, with no `await` in between, drops the
rest: give the loop a turn in long synchronous loops.

## Write a sink

Three class attributes and one method, plus the lifecycle every provider has:

```python
from typing import ClassVar

from etrack.models.event import EventPhase, EventView
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload


class CostSink:
    """Every LLM call's tokens, summed per run."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "cost", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP
    )
    # the fields it reads (→ The record · Views)
    view: ClassVar[type[EventView]] = Cost
    # the phases it wants: no deltas, ever
    phases: ClassVar[frozenset[EventPhase]] = frozenset({EventPhase.END})

    def __init__(self) -> None:
        self.tokens: dict[str, int] = {}

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): ...
    async def health(self) -> bool: return True

    async def send(self, view: Cost) -> None:
        if view.kind == "llm" and view.usage:
            spent = view.usage.total_tokens
            self.tokens[view.run_id] = self.tokens.get(view.run_id, 0) + spent
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
    # frames 42… kept, then every new one, live
    async for frame in live.watch("t1", after=41):
        print(frame.offset, frame.event.kind, frame.event.name)
    # the kept conversations, newest first
    live.threads()
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

