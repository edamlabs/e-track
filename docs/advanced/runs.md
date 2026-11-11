# The run from inside

The code a run calls — a node, a tool, a middleware, a plain function three calls deep — reaches the run without being
handed it. `Tracker.track` binds the run in a context variable for its block; LangGraph carries it into every task.

```python
from etrack.logic.handle import run
```

Outside a run every call below is a no-op: the same code runs tracked and untracked, and never fails for want of a
tracker. Two concurrent runs never cross.

## A span around your code

```python
async def rerank(hits: list[Hit]) -> list[Hit]:
    with run.span("rerank", kind=EventKind.RETRIEVAL, k=5):
        return await model.rank(hits)
```

The span hangs from what is running where it opens — the node, the tool — as the source locates it. Any other keyword
is an attribute of the span. It ends `error` if the block raises (re-raised).

## What the run took in and published

```python
async def speak(state: State) -> dict:
    answer = await voice.say(state)
    run.declare(output=answer.text)
    return {"messages": [answer]}
```

`run.declare(input=…, output=…)` states the run's words from the code that says them. The run's root END carries them as
`input` and `output`, with its `outcome`: `completed`, `interrupted` (an interrupt was raised; a later run resumes it) or
`failed`. Nothing is inferred: a run that declares no output has none, whatever model call came last — a refiner's or a
judge's rewrite is never mistaken for the answer. A word declared again replaces the last. OTLP writes them as
`input.value`, `output.value`, `gen_ai.input.messages`, `gen_ai.output.messages` and `etrack.outcome`. Your mask covers
them as it covers payloads.

## What the run learnt on its way

```python
run.annotate(**{"app.cut": True})     # a guard stopped the turn
```

Attributes annotated during the run land on its root's END, beside what the host put on the root under `app.` (lifted
from the config's metadata). With `Tracker(..., propagate=True)` the root's attributes ride on every frame of the run —
a session, a tenant, a user id that each span's backend should see.

## Facts — business events, typed

```python
from enum import StrEnum, auto
from typing import ClassVar

from etrack.models.fact import Fact


class Area(StrEnum):
    AUTO = auto()
    HOME = auto()


class HandedOver(Fact, frozen=True, kw_only=True):
    labels: ClassVar[frozenset[str]] = frozenset({"area"})
    area: Area
    reason: str


run.fact(HandedOver(area=Area.AUTO, reason="claim over the limit"))
```

A fact is a `msgspec.Struct` subclass: its class is its name, its fields what it carries, `labels` the fields a metric
splits by — closed sets only (an enum, a bool, a `Literal`), so a label never grows a series per value. `run.fact`
validates the value against its class — a field of the wrong type, or a label that is no closed set, raises
`FactError` at the call, tracked or not — and emits one `instant` frame under what is running, with the run's
coordinates. Prometheus counts it in `etrack_fact_handed_over_total{area="auto"}`; OTLP names the span and the log
record's `event_name` after it. `dispatch_custom_event` keeps working, untyped.

## Cost per node and per run

Every model call's usage is added to each node and to the run above it: a node's END carries what the calls under it
spent, the run's END the total. Hand the tracker your prices and each call gets its `cost_usd`:

```python
PRICES = {"gemini-2.5-flash": (0.30e-6, 2.50e-6)}   # per input token, per output token — yours to keep current


def price(model: ModelRef, usage: Usage) -> float | None:
    match PRICES.get(model.name):
        case (inputs, outputs):
            return usage.input_tokens * inputs + usage.output_tokens * outputs
        case _:
            return None


tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter(), pricer=price)
```

The library ships no prices — they age faster than releases. A cost the source already reported stands. Prometheus
counts tokens and cost from model calls only, by `model` and `node`; OTLP writes a node's or a run's totals under
`etrack.usage.*`, so no backend counts a call twice. A sink of your own that summed every frame's `usage` must now read
model calls only (`kind == "llm"`), or the run's END alone.
