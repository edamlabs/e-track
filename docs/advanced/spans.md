# Own spans, facts and masks

The fold that orders the framework's spans takes yours too, in the same tree — a retrieval you run by hand, an
evaluation score, a fact about the run — and every payload passes through your mask first.

```python
import uuid

from etrack.models.event import EventKind
from etrack.ports.source import Edge


def mask(payload: dict) -> dict:
    return {key: "***" if key == "input" else value for key, value in payload.items()}


tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter(), redact=mask)

with tracker.track(thread="t1", config={"metadata": {"app.tenant": "acme"}}) as run:
    await app.ainvoke({"question": "the answer", "answer": ""}, run.config)
    # a span around your code
    with run.fold.span("rerank", kind=EventKind.RETRIEVAL, payload={"k": 5}):
        ...
    # a fact: born closed
    run.fold.instant(
        Edge(
            id=uuid.uuid7().hex,
            kind=EventKind.EVALUATION,
            name="faithfulness",
            payload={"score": 0.92},
        )
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

## Extras — anything else, as structlog takes it

The record has its fields; anything else you hand it travels too, in `attributes`, to every sink — OTLP as span
attributes, the HTTP driver in its body, the forwarded log line flat:

```python
import structlog

# around a whole run: every frame of it, the framework's included
with structlog.contextvars.bound_contextvars(tenant="acme", plan="pro"), tracker.track("t1", config) as run:
    ...
    # on one span of your own
    with run.fold.span("rerank", kind=EventKind.RETRIEVAL, k=5, index="policies"):
        ...

# on one frame you emit
channel.log.info("run.event", run_id=run_id, seq=7, id=span, kind="custom", phase="instant", score=0.92)
```

A key the model declares is a field, never an extra; explicit `attributes` win over a bound key of the same name; a
subclass of the record (→ [The record](record.md)) turns an extra into a typed field.

**Strict mode.** `EventChannel(bus, strict=True)` takes no extras: a key the model does not declare is refused with
`ChannelError`, and bound keys stay off the record — for a pipeline whose consumers expect the schema and nothing else.

## Emit without a framework

Anything that is not a framework can emit straight into the channel — the same validation, the same sinks:

```python
channel.log.info(
    "run.event",
    run_id=run_id, seq=0, id=span, kind="custom", phase="instant", name="deploy",
)
# a RunEvent you built yourself
channel.emit(event)
```

A frame missing a required field raises `ChannelError` naming it.

## `run.fold`

| | |
|---|---|
| `span(name, kind=EventKind.CUSTOM, parent="", payload=None)` | context manager: `start` on entry, `end` on exit, `error` if the block raises (re-raised); yields the span id |
| `instant(Edge(...))` | one frame born closed, under `edge.parent` or the run's root |
| `root` | the run's root span id |
| `scope` | the run's ids |

`Edge` (from `etrack.ports.source`): `id`, `parent`, `kind`, `name`, `payload`, `attributes` — and the graph
coordinates when you have them (`node`, `ns`, `step`).
