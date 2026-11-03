# Quickstart

Three steps on one small graph — no model, no API key: see the events, send them to a backend, watch them live.
Every output below is what the code printed.

```bash
uv add "e-track[all]"
```

## 1 · See the events

A two-node LangGraph graph, tracked, with the smallest possible sink: one that prints every event it receives.

```python
import asyncio
from typing import ClassVar, TypedDict

from langgraph.graph import END, START, StateGraph

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventPhase, EventView, RunEvent
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter


class State(TypedDict):
    question: str
    answer: str


def plan(state: State) -> dict:
    return {"answer": f"looking up {state['question']!r}"}


def answer(state: State) -> dict:
    return {"answer": state["answer"] + " → 42"}


graph = StateGraph(State)
graph.add_node("plan", plan)
graph.add_node("answer", answer)
graph.add_edge(START, "plan")
graph.add_edge("plan", "answer")
graph.add_edge("answer", END)
app = graph.compile()


class PrintSink:
    """The smallest sink: every event, one line."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("print", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = RunEvent                   # what it reads: the whole record
    phases: ClassVar[frozenset[EventPhase]] = frozenset(EventPhase)   # which events reach it: all

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): ...
    async def health(self) -> bool: return True

    async def send(self, event: RunEvent) -> None:
        latency = f"{event.latency_ms:.1f} ms" if event.latency_ms is not None else ""
        print(f"{event.seq}  {event.phase:<5}  {event.kind:<4}  {event.name:<9}  {latency}")


async def main() -> None:
    bus = AnyioAdapter()
    bus.subscribe(PrintSink())
    async with bus:                                              # leaving it delivers what is queued
        tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())
        with tracker.track(thread="t1", config={}) as run:
            result = await app.ainvoke({"question": "the answer", "answer": ""}, run.config)
    print(result["answer"])


asyncio.run(main())
```

```
2026-11-03 17:34:08 [info     ] bus opened                     capacity=1000 sinks=['print']
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb6e773194d01db435461601 kind=run name=LangGraph phase=start run_id=01a1a242cb6e773194d01db435461601 seq=0 thread_id=t1
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb707239aa803e77c8636a01 kind=node name=plan node=plan parent=01a1a242cb6e773194d01db435461601 phase=start run_id=01a1a242cb6e773194d01db435461601 seq=1 step=1 thread_id=t1
0  start  run   LangGraph
1  start  node  plan
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb707239aa803e77c8636a01 kind=node latency_ms=0.754 name=plan node=plan parent=01a1a242cb6e773194d01db435461601 phase=end run_id=01a1a242cb6e773194d01db435461601 seq=2 step=1 thread_id=t1
2  end    node  plan       0.8 ms
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb7170f399a8791ad544cbab kind=node name=answer node=answer parent=01a1a242cb6e773194d01db435461601 phase=start run_id=01a1a242cb6e773194d01db435461601 seq=3 step=2 thread_id=t1
3  start  node  answer
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb7170f399a8791ad544cbab kind=node latency_ms=0.336 name=answer node=answer parent=01a1a242cb6e773194d01db435461601 phase=end run_id=01a1a242cb6e773194d01db435461601 seq=4 step=2 thread_id=t1
4  end    node  answer     0.3 ms
2026-11-03 17:34:08 [info     ] run.event                      id=01a1a242cb6e773194d01db435461601 kind=run latency_ms=2.874 name=LangGraph phase=end run_id=01a1a242cb6e773194d01db435461601 seq=5 thread_id=t1
5  end    run   LangGraph  2.9 ms
2026-11-03 17:34:08 [info     ] bus closed                     dropped={} failed={}
looking up 'the answer' → 42
```

Two streams are interleaved there, and that is the point:

- **The numbered lines are the sink.** The source turned LangGraph's callbacks into events — a `start` and an `end`
  for each span (the run, each node), ordered by `seq`, the `end` carrying its latency — and the bus delivered them to
  `PrintSink` on its own worker. The graph never waited for the printing.
- **The `[info] run.event` lines are your logger.** The channel also writes every event as one line on the structlog
  logger named `etrack`, rendered by your own setup (here structlog's default). `bus opened` / `bus closed` are
  e-track's own lifecycle, on the same logger: `dropped={} failed={}` says no sink lost or refused anything.
- `tracker.track(...)` opened the run and handed back `run.config` — your own config with e-track's callback inside.
  The graph itself is untouched; it only gets a different config.

!!! tip "Only the sink, no log lines"
    `EventChannel(bus, forward=None)` stops the forwarding; filter or route the `etrack` logger like any other to keep
    the lifecycle lines out. → [Logging](guide/logging.md)

## 2 · Send them to a backend

Replace the print sink with the OTLP driver and point it at any OpenTelemetry backend. Locally, Phoenix is one
container:

```bash
docker run -d --rm -p 127.0.0.1:6006:6006 -e PHOENIX_ENABLE_AUTH=false arizephoenix/phoenix:version-21.0.0
```

```python
from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.providers.drivers.sink.otlp import OtlpDriver

settings = OtlpSettings(targets={"phoenix": OtlpTarget(endpoint="http://localhost:6006")})


async def main() -> None:
    async with OtlpDriver(settings) as otlp:                     # closing it flushes the last spans
        bus = AnyioAdapter()
        bus.subscribe(otlp)
        async with bus:
            tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())
            with tracker.track(thread="t1", config={}) as run:
                await app.ainvoke({"question": "the answer", "answer": ""}, run.config)
    print("trace", run.scope.run_id)
```

After the log lines of step 1, it prints:

```
trace 01a1a2421db7776e984ccebf4607414e
```

Phoenix now holds the trace `01a1a242…` with three spans — `LangGraph`, `plan`, `answer` — nested as they ran. The
run id **is** the trace id: the same run carries the same name in every backend, in the viewer and in your logs.

In production the targets come from the environment, not from code — `OtlpDriver()` reads them:

```bash
ETRACK_OTLP_TARGETS='{"langfuse": {"endpoint": "https://cloud.langfuse.com/api/public/otel",
                                   "headers": {"Authorization": "Basic <base64 of pk:sk>"}}}'
```

Several targets receive everything at once. → [Backends](guide/backends.md)

## 3 · Watch them live

Subscribe the live buffer, read the graph once, serve the viewer:

```python
from etrack.logic.viewer import Viewer
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter


async def main() -> None:
    async with LiveAdapter() as live:
        bus = AnyioAdapter()
        bus.subscribe(live)
        async with bus:
            viewer = Viewer(watch=live, topology=LanggraphTopologyAdapter().read(app))
            async with GranianAdapter(viewer.app) as server:
                print("viewer at", server.url)
                tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())
                with tracker.track(thread="t1", config={}) as run:
                    await app.ainvoke({"question": "the answer", "answer": ""}, run.config)
                await asyncio.Event().wait()                     # keep serving
```

Among the log lines, `server opened url=http://127.0.0.1:28130` and:

```
viewer at http://127.0.0.1:28130
```

Open it: the graph as declared, each node lit while it runs, and the conversation in the thread picker.
→ [Viewer](guide/viewer.md)

## Where to go next

| You want to… | Read |
|---|---|
| know what an event holds | [The record](guide/record.md) |
| track spans of your own code, mask payloads, pin a run id | [Tracking runs](guide/tracking.md) |
| choose what each sink receives, write your own | [Sinks](guide/sinks.md) |
| send to Langfuse, LangSmith, Phoenix, Tempo | [Backends](guide/backends.md) |
| embed the viewer in your app | [Viewer](guide/viewer.md) |
| configure it all from the environment | [Settings](guide/settings.md) |
