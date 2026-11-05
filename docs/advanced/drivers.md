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

Any other refusal (400, 401, 413…) is not retried. A refused batch is dropped and counted (`failed`), raised to the bus
when a full batch was sent from `send` — so it shows in `bus.failed` — and logged as `http flush failed` when the timer
sent it. Leaving the driver sends what is left. `sent` counts what was delivered.

## Build your own

Subclass it and override only what your endpoint needs:

| Override | Default | |
|---|---|---|
| `view` | `RunEvent` | the fields you read: the bus narrows every event onto it before `send` |
| `phases` | start, end, error, instant | the phases you want: the bus skips the rest before queueing |
| `spec` | `http` | your driver's name in the bus's counters and the logs |
| `accept(view)` | the configured kinds | whether this event is sent at all |
| `encode(view)` | the view itself | what the event becomes in the batch: a struct, a dict, anything msgspec encodes |
| `body(items)` | the configured encoding | the request body and its content type |

Batching, timing, signing, retrying and the lifecycle stay the driver's.

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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
    - `429` with `Retry-After` when busy, `5xx` on its own failure — both retried; `400` for a malformed line rejects
      the batch, `413` when a batch is too large (lower `batch`) — neither retried.
    - Answers within `ETRACK_HTTP_TIMEOUT` (10 s): store first, score later — the run is never waiting on it, but the
      bus's queue for this sink is.
    - Optional and cheap to add: `run_id`/`thread_id` indexed, so the service can tell which conversation a recall
      served and join it with the run's trace (`run_id` is the trace id in every backend).
