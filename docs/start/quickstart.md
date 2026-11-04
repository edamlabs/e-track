# Quickstart

Three steps on one small graph — no model, no API key: see the events, send them to a backend, watch them live.
Every output below is what the code printed; e-track's log lines on your logger are left out here.

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

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "print", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP
    )
    # what it reads: the whole record
    view: ClassVar[type[EventView]] = RunEvent
    # which events reach it: all
    phases: ClassVar[frozenset[EventPhase]] = frozenset(EventPhase)

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): ...
    async def health(self) -> bool: return True

    async def send(self, event: RunEvent) -> None:
        latency = f"{event.latency_ms:.1f} ms" if event.latency_ms is not None else ""
        line = f"{event.seq}  {event.phase:<5}  {event.kind:<4}  {event.name:<9}"
        print(f"{line}  {latency}")


async def main() -> None:
    bus = AnyioAdapter()
    bus.subscribe(PrintSink())
    # leaving it delivers what is queued
    async with bus:
        tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())
        with tracker.track(thread="t1", config={}) as run:
            question = {"question": "the answer", "answer": ""}
            result = await app.ainvoke(question, run.config)
    print(result["answer"])


asyncio.run(main())
```

```
0  start  run   LangGraph
1  start  node  plan
2  end    node  plan       0.8 ms
3  start  node  answer
4  end    node  answer     0.3 ms
5  end    run   LangGraph  2.9 ms
looking up 'the answer' → 42
```

What happened:

- **The sink.** The source turned LangGraph's callbacks into events — a `start` and an `end`
  for each span (the run, each node), ordered by `seq`, the `end` carrying its latency — and the bus delivered them to
  `PrintSink` on its own worker. The graph never waited for the printing.
- **Your logger.** Interleaved with these lines, the run also printed one `run.event` line per event on structlog's
  `etrack` logger, and e-track's own `bus opened` / `bus closed` — what they look like and how to route them:
  [Logging](../advanced/logging.md).
- `tracker.track(...)` opened the run and handed back `run.config` — your own config with e-track's callback inside.
  The graph itself is untouched; it only gets a different config.

!!! tip "Only the sink, no log lines"
    `EventChannel(bus, forward=None)` stops the forwarding; filter or route the `etrack` logger like any other to keep
    the lifecycle lines out. → [Logging](../advanced/logging.md)

## 2 · Send them to a backend

Replace the print sink with the OTLP driver and point it at any OpenTelemetry backend. Locally, Phoenix is one
container:

```bash
docker run -d --rm -p 127.0.0.1:6006:6006 -e PHOENIX_ENABLE_AUTH=false \
  arizephoenix/phoenix:version-21.0.0
```

```python
from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.providers.drivers.sink.otlp import OtlpDriver

phoenix = OtlpTarget(endpoint="http://localhost:6006")
settings = OtlpSettings(targets={"phoenix": phoenix})


async def main() -> None:
    # closing it flushes the last spans
    async with OtlpDriver(settings) as otlp:
        bus = AnyioAdapter()
        bus.subscribe(otlp)
        async with bus:
            tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())
            with tracker.track(thread="t1", config={}) as run:
                question = {"question": "the answer", "answer": ""}
                await app.ainvoke(question, run.config)
    print("trace", run.scope.run_id)
```

It prints:

```
trace 01a1a2421db7776e984ccebf4607414e
```

Phoenix now holds the trace `01a1a242…` with three spans — `LangGraph`, `plan`, `answer` — nested as they ran. The
run id **is** the trace id: the same run carries the same name in every backend, in the viewer and in your logs.

In production the targets come from the environment, not from code — `OtlpDriver()` reads them:

```bash
ETRACK_OTLP_TARGETS='{"langfuse": {
  "endpoint": "https://cloud.langfuse.com/api/public/otel",
  "headers": {"Authorization": "Basic <base64 of pk:sk>"}}}'
```

Several targets receive everything at once. → [Send events](../basics/events.md)

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
                    question = {"question": "the answer", "answer": ""}
                await app.ainvoke(question, run.config)
                # keep serving
                await asyncio.Event().wait()
```

It prints:

```
viewer at http://127.0.0.1:28130
```

Open it: the graph as declared, each node lit while it runs, and the conversation in the thread picker.
→ [Watch it live](../basics/viewer.md)

## Where to go next

| You want to… | Read |
|---|---|
| understand the three objects and `track` | [Track a run](../basics/tracking.md) |
| send to several places at once | [Send events](../basics/events.md) |
| use the viewer: pickers, node cards, colours | [Watch it live](../basics/viewer.md) |
| know what an event holds | [The record](../advanced/record.md) |
| track spans of your own code, mask payloads | [Own spans](../advanced/spans.md) |
| write your own sink | [Custom sinks](../advanced/sinks.md) |
| name nodes for people, read other graphs | [Graphs & labels](../advanced/graphs.md) |
| send to Langfuse, Phoenix, LangSmith, Tempo | [Integrations](../integrations/langfuse.md) |
| embed the viewer in your app | [Web apps](../integrations/web.md) |
| see every class and its import | [API at a glance](../reference/api.md) |
