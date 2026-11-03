# Introduction

An agent run is a tree of spans: the run, its nodes, the model calls and tool calls under them, the subagents they
delegate to. Every framework reports that tree its own way, and every backend wants it its own way. e-track puts one
record between them.

```
framework hooks ─► source ─► fold ─► channel (validate → publish → forward to host logger)
                                                 │
                                                 └─► bus ─┬─► otlp   spans + logs → Langfuse · LangSmith · Tempo · Phoenix
                                                          ├─► live   per-thread replay + push → a canvas, a chat
                                                          └─► yours  any SinkPort, any EventView
```

| Piece | Is | Module |
|---|---|---|
| source | a framework's hooks reported as span edges | `etrack.providers.adapters.source.langgraph` |
| fold | edges folded into ordered, parented, stamped frames | `etrack.processors.fold` |
| channel | the log that carries the frames: validate, publish, forward | `etrack.logic.channel` |
| bus | one bounded stream and one worker per sink | `etrack.providers.adapters.bus.anyio` |
| sinks | the clients: OTLP over the wire, live in memory, yours | `etrack.providers.{drivers,adapters}.sink` |
| tracker | the public surface: one run from a host's config | `etrack.logic.api` |

## The record

| Field | What |
|---|---|
| `run_id`, `thread_id` | the run (32 hex, also the W3C trace id) and the conversation |
| `seq`, `id`, `parent` | order within the run; the span and its visible parent |
| `kind` | `run agent subagent node llm embedding retrieval tool mcp interrupt state evaluation custom` |
| `phase` | `start delta end error instant` |
| `part` | on deltas: `text reasoning tool_call image audio video file custom` |
| `node`, `ns`, `step`, `visit` | graph coordinates: node, subgraph path, superstep, times the run entered the node |
| `message_id`, `call_id` | the chat message and the tool call a client renders |
| `model`, `usage`, `error` | typed sections: provider/name/params, tokens/cost, failure |
| `payload`, `attributes` | what the span carried (redacted); the open, namespaced extension bag |

Grow it by subclassing `RunEvent` and passing the subclass to `EventChannel(model=…)`; read it through an
`EventView`: a client declares the fields it needs and `View.project(event)` narrows any event onto it.

## The layers

The package follows the house taxonomy: `models` (the record) and `ports` (the contracts) at the floor; `providers`
— `drivers` when the work happens outside the process (OTLP), `adapters` when a library runs inside it (anyio,
LangGraph, the live buffer); `processors` that transform (fold, layout); `logic`, the public surface. Layers import
only downward: `tach` and `tests/unit/test_taxonomy.py` hold the table, and every foreign framework enters through
the one module that owns it.
