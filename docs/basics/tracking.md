# Track a run

Three objects, built once at startup; one `with` per run.

```python
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter

# carries the events to the sinks
bus = AnyioAdapter()
tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())

async with bus:
    # one run of one conversation
    with tracker.track(thread="t1", config={}) as run:
        # your graph, untouched
        await graph.ainvoke(inputs, run.config)
```

| Object | Is | Build it |
|---|---|---|
| `AnyioAdapter` | the bus: one queue and one worker per sink | once; subscribe sinks to it ([Send events](events.md)) |
| `EventChannel` | validates every frame, publishes it, logs a line | once, over the bus |
| `LanggraphSourceAdapter` | reads LangGraph's callbacks | once ([LangGraph](../integrations/langgraph.md)) |
| `Tracker` | opens runs | once |

## `tracker.track`

```python
with tracker.track(thread="t1", config={"configurable": {"thread_id": "t1"}}) as run:
    await graph.ainvoke(inputs, run.config)
    # 01a1a242cb6e773194d01db435461601 — the trace id in every backend
    print(run.scope.run_id)
```

| kwarg | type | default | |
|---|---|---|---|
| `thread` | `str` | — | the conversation; every event carries it, the viewer lists by it |
| `config` | your `RunnableConfig` | — | returned as `run.config` with the hook inside; your callbacks and metadata are kept |
| `run_id` | `str \| None` | a new uuid7 | pin an id you already chose |

| `run.` | |
|---|---|
| `config` | what you pass to the graph |
| `scope.run_id`, `scope.thread_id` | the run's ids |
| `fold` | spans and facts of your own code → [Own spans](../advanced/spans.md) |

Inside the block, structlog's contextvars carry `run_id` and `thread_id`: your own log lines are tagged with the run.

## What you get

Every span of the run, as events — a deep agent delegating to a subagent that calls an MCP tool, each `start`
printed under its parent:

```
run      LangGraph
  node     PatchToolCallsMiddleware.before_agent
  node     model
    llm      ScriptedModel
  node     tools
    subagent ontologo
      node     PatchToolCallsMiddleware.before_agent
      node     model
        llm      ScriptedModel
      node     tools
        mcp      onto_query
      node     model
        llm      ScriptedModel
  node     model
    llm      ScriptedModel
  node     _ParentNotifierMiddleware.after_agent
```

Each span is a `start` and an `end` (or `error`), streamed pieces in between as `delta`s. What an event holds →
[The record](../advanced/record.md).
