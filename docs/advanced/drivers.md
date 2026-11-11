# Custom drivers

`HttpDriver` sends events to any HTTP endpoint: batched, signed, retried. Use it as it is to feed a system that takes
JSON, or build a driver of your own on it — a memory service, a webhook, an internal collector — by overriding only what
differs. Install `e-track[http]`.

## As it is

```python
from pydantic import SecretStr

from etrack.infra.config.auth import BearerAuth
from etrack.providers.drivers.sink.http import HttpDriver

async with HttpDriver(endpoint="https://events.internal/v1/ingest", auth=BearerAuth(token=SecretStr("…"))) as http:
    bus.subscribe(http)
    ...
```

Or from the environment, with `HttpDriver()`:

| Setting | default | |
|---|---|---|
| `ETRACK_HTTP_ENDPOINT` | `""` | the URL every batch is sent to |
| `ETRACK_HTTP_METHOD` | `POST` | `POST` or `PUT` |
| `ETRACK_HTTP_AUTH` | none | how it signs → [Authentication](auth.md) |
| `ETRACK_HTTP_HEADERS` | `{}` | fixed headers, as JSON |
| `ETRACK_HTTP_ENCODING` | `ndjson` | `ndjson` (one event per line) or `json` (one array) |
| `ETRACK_HTTP_BATCH` | `100` | events per request at most — a full batch leaves at once |
| `ETRACK_HTTP_FLUSH` | `1s` | the longest an event waits for its batch |
| `ETRACK_HTTP_TIMEOUT` | `10s` | per request |
| `ETRACK_HTTP_RETRIES` | `3` | attempts after the first, on a network error, 408, 425, 429 or 5xx |
| `ETRACK_HTTP_BACKOFF` | `500ms` | the first wait between attempts, doubled each time |
| `ETRACK_HTTP_KINDS` | all | the kinds sent, as a JSON list (`["llm", "retrieval"]`) |
| `ETRACK_HTTP_SCHEDULE` | `1m, 5m, 30m, 2h, 6h` | with an outbox: the wait before each new attempt, the last repeating (JSON list of durations) |
| `ETRACK_HTTP_DEADLINE` | `24h` | with an outbox: how long an item is tried before it is dead |
| `ETRACK_HTTP_LEASE` | `5m` | with an outbox: how long a claim is held — a relay that dies leaves it due again after |
| `ETRACK_HTTP_POLL` | `1s` | with an outbox: how often the relay looks for what is due |

Any other refusal (400, 401, 413, 422…) is final, never retried — and a batch refused for good is sent again item by
item, so one bad item costs one item, never its batch. What is refused in the end is counted (`failed`) and handed to
`refused(items, refusal)` — a `Refusal` with the status (0 for a network failure), the server's reason and `final` —
which logs `http refused` by default; nothing is raised in the bus's way. Leaving the driver sends what is left. `sent`
counts what was delivered; `report()` says it all at once.

## Build your own

Subclass it and override only what your endpoint needs:

| Override | Default | |
|---|---|---|
| `view` | `RunEvent` | the fields you read: the bus narrows every event onto it before `send` |
| `phases` | start, end, error, instant | the phases you want: the bus skips the rest before queueing |
| `spec` | `http` | your driver's name in the bus's counters and the logs |
| `accept(view)` | the configured kinds | whether this event is sent at all — your gate, which fails closed (below) |
| `encode(view)` | the view itself | what the event becomes in the batch: a struct, a dict, anything msgspec encodes |
| `body(items)` | the configured encoding | the request body and its content type |
| `refused(items, refusal)` | a warning | what to do with what the endpoint did not take |
| `key(view, content)` | the content's hash | with an outbox: the key an item is stored and deduplicated by |

Batching, timing, signing, retrying and the lifecycle stay the driver's. To sign with an identity of your own — a token
your platform mints, a service account you already hold — hand the driver any object with `async headers()`:
`HttpDriver(signer=my_identity, …)`; it signs every request instead of the configured `auth`.

## One item per run, through a gate

A run's root END carries what a run-level consumer needs: what the run declared it took in and published, how it
ended, the host's `app.*` attributes and the ones annotated on the way (→ [The run from inside](runs.md)). Read it
with `RunView`, and write the rule in `accept`:

```python
from etrack.models.event import EventPhase, EventView, Outcome, RunView


class TurnDriver(HttpDriver):
    view = RunView
    phases = frozenset({EventPhase.END, EventPhase.ERROR})

    def accept(self, view: EventView) -> bool:
        turn = RunView.project(view)
        return (
            turn.ended
            and turn.outcome is Outcome.COMPLETED
            and turn.attributes["app.consent.memory"] is True
            and turn.attributes["app.owner"] != "anonymous"
        )

    def encode(self, view: EventView) -> dict:
        turn = RunView.project(view)
        return {"turn_id": turn.run_id, "thread_id": turn.thread_id, "user": turn.input, "assistant": turn.output}
```

The gate fails closed: an `accept` that reads a key the run does not carry (`turn.attributes["app.owner"]` on a run
nobody gave an owner) refuses the run and counts it in `missing` — a missing fact never passes as a default. The
library holds no rule; the rule is yours.

## Guaranteed delivery

Hand the driver an outbox and nothing it accepted is lost to an outage, a refusal worth retrying, or a restart:

```python
from pathlib import Path

from etrack.ports.bus import Delivery
from etrack.providers.adapters.outbox.sqlite import SqliteAdapter

async with SqliteAdapter(Path("/var/lib/app/outbox.db")) as outbox, TurnDriver(outbox=outbox, endpoint=…) as turns:
    bus.subscribe(turns, delivery=Delivery.GUARANTEED)
```

- `send` stores each item under its `key` before any network call; override `key` with the id your receiver
  deduplicates by (a turn id). Delivery is **at least once**: the receiver's deduplication makes it once in effect.
- A relay delivers what is due. A refusal worth another attempt waits the next step of `ETRACK_HTTP_SCHEDULE`; an item
  still undelivered past `ETRACK_HTTP_DEADLINE`, or refused for good, is **dead**, with its reason, and handed to
  `refused`. `outbox.of(key)` shows where an item stands; `outbox.requeue(key)` sends a dead one again.
- `Delivery.GUARANTEED` gives the subscription a queue that never drops: subscribe that way only a sink that takes few
  phases (a run's END).
- `SqliteAdapter` is the reference store: one SQLite file, standard library, committed with `synchronous=FULL` — an
  append survives a killed process and a lost machine (~6 ms each on NVMe; → [Decisions](../decisions.md)). A host with
  a job table of its own meets `OutboxPort` with it.

**The boundary.** The guarantee begins when the item is stored — on the run's END. A process that dies in the middle of
a run stored nothing of it: its frames were in memory. A host that needs more reconciles from its own checkpoint.

### Example — a memory service recording recall

An agent recalls from a memory service — e-gnosis's `kb_find` and `kb_chunk`, findr-ground's search — through MCP tools.
The memory service wants to know what was recalled, by whom, how fast and whether it helped: hits that are recalled
again and again rise, entries never recalled fade. The driver reads the recall calls off the run and sends them back:

```python
from typing import Any, ClassVar

import msgspec

from etrack.models.event import EventKind, EventPhase, EventView
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.providers.drivers.sink.http import HttpDriver

RECALLS = frozenset({"kb_find", "kb_chunk", "kb_section"})


class RecallView(EventView, frozen=True, kw_only=True):
    """What a recall record needs of a frame."""

    run_id: str
    thread_id: str = ""
    id: str
    kind: EventKind
    phase: EventPhase
    name: str = ""
    latency_ms: float | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)


class Recall(msgspec.Struct, frozen=True, kw_only=True):
    """One recall, as the memory service stores it."""

    id: str
    run_id: str
    thread_id: str
    tool: str
    query: Any
    answer: Any
    latency_ms: float | None


class RecallDriver(HttpDriver):
    """Every recall the agents make, sent to the memory service that answered it."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "recall", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True
    )
    view: ClassVar[type[EventView]] = RecallView
    # the question travels on the call's start, the answer on its end
    phases: ClassVar[frozenset[EventPhase]] = frozenset({EventPhase.START, EventPhase.END})

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.asked: dict[str, Any] = {}

    def accept(self, view: EventView) -> bool:
        view = RecallView.project(view)
        if view.kind is not EventKind.MCP or view.name not in RECALLS:
            return False
        if view.phase is EventPhase.START:
            # keep the question until its answer arrives; nothing is sent yet
            self.asked[view.id] = view.payload.get("input")
            return False
        return view.id in self.asked

    def encode(self, view: EventView) -> Recall:
        view = RecallView.project(view)
        return Recall(
            id=view.id,
            run_id=view.run_id,
            thread_id=view.thread_id,
            tool=view.name,
            query=self.asked.pop(view.id),
            answer=view.payload.get("output"),
            latency_ms=view.latency_ms,
        )
```

```python
recall = RecallDriver(
    endpoint="http://127.0.0.1:8765/v1/recalls",
    auth=BearerAuth(token=SecretStr("…")),
    batch=50,
    flush=timedelta(seconds=2),
)
async with recall:
    bus.subscribe(recall)
```

A tool call's start carries its arguments (`payload["input"]`), its end what it answered (`payload["output"]`): the
driver pairs them by span id. What `query` and `answer` hold is whatever your memory tools take and return.

!!! note "TODO — the endpoint a memory service exposes for this"
    No memory service takes recall records yet. What the driver above expects of it:

    - `POST /v1/recalls`, `Content-Type: application/x-ndjson`, one `Recall` per line; `Authorization: Bearer`.
    - **Idempotent on `id`** (the span's id): a batch retried after a timeout must not count a recall twice.
    - `202 Accepted` with `{"accepted": <n>}` once stored; the driver only reads the status.
    - `429` with `Retry-After` when busy, `5xx` on its own failure — both retried; `400` for a malformed line refuses
      the batch, which the driver then sends item by item; `413` when a batch is too large (lower `batch`) — neither
      retried.
    - Answers within `ETRACK_HTTP_TIMEOUT` (10 s): store first, score later — the run is never waiting on it, but the
      bus's queue for this sink is.
    - Optional and cheap to add: `run_id`/`thread_id` indexed, so the service can tell which conversation a recall
      served and join it with the run's trace (`run_id` is the trace id in every backend).
