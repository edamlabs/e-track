# Tracking runs

A run is tracked by handing your framework a config with e-track's hook inside. The graph is never wrapped, subclassed
or rebuilt.

```python
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter

tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))

with tracker.track(thread="t1", config={"configurable": {"thread_id": "t1"}}) as run:
    await agent.ainvoke({"messages": [("user", "what is a policy?")]}, run.config)
```

## `Tracker`

| kwarg | type | default | |
|---|---|---|---|
| `channel` | `EventChannel` | — | where the frames go (→ [Sinks](sinks.md)) |
| `source` | a `SourcePort` | — | the framework's reader: `LanggraphSourceAdapter` |
| `redact` | `(dict) -> dict` | none | your mask over every payload, before any sink sees it |

## `tracker.track`

| kwarg | type | default | |
|---|---|---|---|
| `thread` | `str` | — | the conversation; every frame carries it, the viewer lists by it |
| `config` | the framework's config (`RunnableConfig`) | — | returned with the hook bound; your callbacks and metadata are kept |
| `run_id` | `str \| None` | a new uuid7 | pin a run id you already chose |

It yields a `Tracked`: `run.config` (what you pass to the framework), `run.scope.run_id` (the run's id, also the
trace id in every backend) and `run.fold` (for spans of your own code, below). Inside the block, structlog's
contextvars carry `run_id` and `thread_id`, so every log line you write there is tagged with the run.

## What a LangGraph run looks like

A deep agent delegating to a subagent, which calls an MCP tool — every `start` frame of the run, indented by its
`parent`:

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

The subagent's own graph nests under the `task` call that launched it; `onto_query` is an `mcp` span because it was
declared in `mcp=`.

## `LanggraphSourceAdapter`

| kwarg | type | default | |
|---|---|---|---|
| `mcp` | `frozenset[str]` | `∅` | tool names that are MCP calls: their spans are `mcp`, not `tool` |
| `subagents` | `frozenset[str]` | `{"task"}` | tools that delegate to a subagent, named by their `subagent_type` argument |

It reads LangChain's callbacks inline, on the caller's thread — no queue, no thread hop — and pins the run's id as
LangChain's root run id, so LangSmith and e-track name the run alike.

## Spans, facts and masks of your own

The fold that orders the framework's spans takes yours too, in the same tree:

```python
import uuid

from etrack.models.event import EventKind
from etrack.ports.source import Edge


def mask(payload: dict) -> dict:
    return {key: "***" if key == "input" else value for key, value in payload.items()}


tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter(), redact=mask)

with tracker.track(thread="t1", config={"metadata": {"app.tenant": "acme"}}) as run:
    await app.ainvoke({"question": "the answer", "answer": ""}, run.config)
    with run.fold.span("rerank", kind=EventKind.RETRIEVAL, payload={"k": 5}):     # a span around your code
        ...
    run.fold.instant(                                                               # a fact: born closed
        Edge(id=uuid.uuid7().hex, kind=EventKind.EVALUATION, name="faithfulness", payload={"score": 0.92})
    )
```

Every frame, with its payload:

```
0  start    run         LangGraph     {'input': '***'}
1  start    node        plan          {}
2  end      node        plan          {'keys': ['answer']}
3  start    node        answer        {}
4  end      node        answer        {'keys': ['answer']}
5  end      run         LangGraph     {'keys': ['answer', 'question']}
6  start    retrieval   rerank        {'k': 5}
7  end      retrieval   rerank        {}
8  instant  evaluation  faithfulness  {'score': 0.92}
```

- `redact` masked the run's input before any sink saw it.
- `run.fold.span(...)` opened and closed a span around the block — `error` instead of `end` if the block raises, the
  exception re-raised. It yields the span's id, to nest further spans under it (`parent=`).
- `run.fold.instant(...)` recorded a fact under the run's root.
- The `app.tenant` metadata landed on the root span's `attributes` (`{'app.tenant': 'acme'}`): put a run's own facts —
  agent version, tenant, experiment arm — under `app.` and every backend sees them. A node's state outputs are
  reported by their keys, not their values: what a span carried in full is the model's and the tools' payloads.

## Emitting by hand

Anything that is not a framework can emit straight into the channel — the same validation, the same sinks:

```python
channel.log.info("run.event", run_id=run_id, seq=0, id=span, kind="custom", phase="instant", name="deploy")
channel.emit(event)                                   # a RunEvent you built yourself
```

A frame missing a required field raises `ChannelError` naming it.
