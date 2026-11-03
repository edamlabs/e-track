# Usage

The public surface, one section per piece: the tracker, the channel, the bus, the source, the sinks, the layout.

## `Tracker.track`

```python
with tracker.track("t1", config) as run:      # run.scope.run_id == LangChain's root run id
    await graph.ainvoke(inputs, run.config)
```

| kwarg | type | default | |
|---|---|---|---|
| `thread` | `str` | — | the conversation; every frame carries it |
| `config` | the source's config (`RunnableConfig`) | — | returned with the source's hook bound |
| `run_id` | `str \| None` | uuid7 hex | pin a run id the host already chose |

## `EventChannel`

```python
channel.emit(event)                                        # a record already built
channel.log.info("run.event", run_id=…, seq=…, id=…, kind="custom", phase="instant")   # reserved keys
```

| kwarg | type | default | |
|---|---|---|---|
| `bus` | `BusPort` | — | where validated records go |
| `model` | `type[RunEvent]` | `RunEvent` | a project's subclass to validate into |
| `forward` | `type[EventView] \| None` | `LogView` | what reaches the host's `etrack` logger; `None`: nothing |

## `AnyioAdapter`

```python
bus.subscribe(sink, select=lambda event: None if event.part is Part.REASONING else event)
```

`publish` never waits: a full sink drops (`bus.dropped`), a raising sink is skipped (`bus.failed`). Setting:
`ETRACK_BUS_CAPACITY` (1000). A synchronous burst longer than the capacity, with no await in between, drops the rest.

## `LanggraphSourceAdapter`

| kwarg | type | default | |
|---|---|---|---|
| `mcp` | `frozenset[str]` | `∅` | tool names that are MCP calls |
| `subagents` | `frozenset[str]` | `{"task"}` | tools that delegate to a subagent (named by `subagent_type`) |

| LangChain sees | frame |
|---|---|
| root chain | `run` |
| chain named after its `langgraph_node` | `node` (one span for a mounted subgraph) |
| chat model / LLM | `llm` + deltas typed by v1 content block |
| tool · MCP tool · `task` | `tool` · `mcp` · `subagent` |
| retriever | `retrieval` |
| `GraphInterrupt` | `interrupt` instant, once, under the span that raised |
| `dispatch_custom_event` | `custom` instant |

## `LiveAdapter`

```python
async for frame in live.watch("t1", after=last_offset):   # replay, then follow
    send(frame.offset, frame.event)
```

Settings: `ETRACK_LIVE_BUFFER` (2000 per thread), `ETRACK_LIVE_THREADS` (256), `ETRACK_LIVE_BACKLOG` (1000).

## `OtlpDriver`

| Setting | default | |
|---|---|---|
| `ETRACK_OTLP_TARGETS` | `{}` | `{"name": {"endpoint": base, "headers": {…}}}` — `/v1/traces`, `/v1/logs` appended |
| `ETRACK_OTLP_TRACES` / `_LOGS` | `true` / `false` | which signals leave |
| `ETRACK_OTLP_FLUSH` / `_TIMEOUT` | `1s` / `10s` | batch cadence, export deadline |
| `ETRACK_OTLP_SERVICE` | `etrack` | `service.name` |

Trace id = run id; span id = the frame id's low 64 bits. `driver.processor()` is a structlog processor the host may add
to its own chain so its application logs leave as OTel records too.

## `LayoutProcessor`

```python
placed = LayoutProcessor().place(LanggraphTopologyAdapter().read(graph))   # rank, lane, loop
```

## `LiveAdapter`

```python
async for frame in live.watch("t1", after=last_offset):    # replay what is kept past the cursor, then follow
    await websocket.send_bytes(msgspec.json.encode(frame))
```

| setting | default | |
|---|---|---|
| `ETRACK_LIVE_BUFFER` | `2000` | frames kept per thread for a reconnect to replay |
| `ETRACK_LIVE_THREADS` | `256` | threads kept; the least recently written is evicted first |
| `ETRACK_LIVE_BACKLOG` | `1000` | frames a watcher may lag before it is cut off |

## `OtlpDriver`

Every target receives every span; with `logs`, every frame is also a log record on its span. Each span speaks
OpenTelemetry GenAI (`gen_ai.*`), OpenInference (`openinference.span.kind`, `llm.*`) and Langfuse
(`langfuse.observation.type`) at once.

```bash
ETRACK_OTLP_TARGETS='{"phoenix": {"endpoint": "http://localhost:6006"},
                      "langfuse": {"endpoint": "https://cloud.langfuse.com/api/public/otel",
                                   "headers": {"Authorization": "Basic <base64 pk:sk>"}}}'
ETRACK_OTLP_LOGS=true
```

| setting | default | |
|---|---|---|
| `ETRACK_OTLP_TARGETS` | `{}` | collectors by name; none: spans are minted, never exported |
| `ETRACK_OTLP_TRACES` · `ETRACK_OTLP_LOGS` | `true` · `false` | which signals leave |
| `ETRACK_OTLP_TIMEOUT` · `ETRACK_OTLP_FLUSH` | `10s` · `1s` | per-export deadline, batch period |
| `ETRACK_OTLP_SERVICE` | `etrack` | `service.name` |
| `ETRACK_OTLP_ATTRIBUTES` | `{}` | extra resource attributes (`openinference.project.name`, …) |

`otlp.processor()` is a structlog processor for the host's own chain: every host log line also leaves as an OTel
log record.

## `LayoutProcessor`

```python
topology = LayoutProcessor().place(LanggraphTopologyAdapter().read(graph))   # ranks, lanes, loops marked
```

O(V + E) for loops and ranks, O(V log V) for lanes (rustworkx): back edges close cycles, topological generations are
the ranks, a barycenter pass orders each rank.
