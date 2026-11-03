# The record

Everything e-track produces is one type: `RunEvent`, one frame per edge of a span — a span starts, streams a piece,
ends, fails, or happens at once. Every sink, every backend and the viewer read this record and nothing else.

```python
from etrack.models.event import EventKind, EventPhase, Part, RunEvent
```

## A frame

An LLM call's `end` frame, as a sink receives it (the values are illustrative; the shape is the record's):

```json
{
  "v": 1,
  "run_id": "019a4f1c8e2b7d3a9c5e0f1a2b3c4d5e",
  "thread_id": "t1",
  "seq": 7,
  "id": "019a4f1c8e2b7f10a3b4c5d6e7f80912",
  "parent": "019a4f1c8e2b7e01b2c3d4e5f6a7b8c9",
  "kind": "llm",
  "phase": "end",
  "name": "gpt-5",
  "node": "agent",
  "ns": "",
  "step": 2,
  "visit": 1,
  "part": null,
  "message_id": "019a4f1c8e2b7f10a3b4c5d6e7f80912",
  "call_id": "",
  "at": "2026-11-03T16:31:21.383195Z",
  "latency_ms": 812.4,
  "model": {"provider": "openai", "name": "gpt-5", "params": {"temperature": 0}},
  "usage": {
    "input_tokens": 1840, "output_tokens": 96, "total_tokens": 1936,
    "reasoning_tokens": 0, "cache_read_tokens": 1536, "cache_write_tokens": 0, "cost_usd": null
  },
  "error": null,
  "payload": {"text": "Una póliza es seg:Poliza.", "reasoning": "", "tool_calls": []},
  "attributes": {}
}
```

## The fields

| Field | What it says |
|---|---|
| `run_id` | the run — 32 hex, uuid7. It is also the W3C trace id: Langfuse, Phoenix, the viewer and your logs name the run alike |
| `thread_id` | the conversation the run belongs to; several runs share it |
| `seq` | the frame's order within the run, from 0, contiguous |
| `id`, `parent` | the span and its visible parent: any client rebuilds the tree from these two |
| `kind` | what the span is (below) |
| `phase` | where the span is in its life (below) |
| `part` | on `delta` frames only: what the streamed piece carries (below) |
| `name` | the node's, model's, tool's or subagent's name |
| `node`, `ns`, `step`, `visit` | graph coordinates: the node a span runs under, its subgraph path, the superstep, how many times the run entered that node |
| `message_id`, `call_id` | the chat message and the tool call a UI renders the frame into |
| `at`, `latency_ms` | when, in UTC; how long the span took (on `end` and `error`) |
| `model` | which model served an LLM call: provider, name, request parameters |
| `usage` | tokens by kind — input, output, reasoning, cache read/write — and cost when known |
| `error` | why a span failed: the exception's type and message |
| `payload` | what the span carried: inputs on `start`, outputs on `end`, the piece on `delta` — after your redaction |
| `attributes` | the open extension bag, namespaced by its owner (`app.*` for the run's own facts, `etrack.*`) |

## Kind — what the span is

| `kind` | A span that… | From LangGraph |
|---|---|---|
| `run` | is the whole run | the root chain |
| `node` | is a graph node | a chain named after its own `langgraph_node` |
| `llm` | calls a model | a chat model or LLM |
| `tool` | calls a tool | a tool |
| `mcp` | calls a tool served over MCP | a tool whose name you declared in `mcp=` |
| `subagent` | delegates to a subagent | the deep agent's `task` tool, named by `subagent_type` |
| `retrieval` | retrieves documents | a retriever |
| `embedding` | embeds | — (your own spans) |
| `interrupt` | pauses for a human | a `GraphInterrupt`, once, under the span that raised it |
| `state`, `evaluation` | records a state, a score | — (your own instants) |
| `agent` | is an agent | — |
| `custom` | anything else | `dispatch_custom_event`, and the fallback |

Plumbing — sequences, middleware wrappers — is folded away: a frame's `parent` is always a span that was itself
emitted.

## Phase — where it is in its life

| `phase` | Means |
|---|---|
| `start` | the span opened; `payload` holds its input |
| `delta` | a streamed piece of an open span: a token, a reasoning chunk, a tool call's arguments |
| `end` | the span closed; `payload` holds its output, `latency_ms` and `usage` are set |
| `error` | the span failed; `error` says why |
| `instant` | a span born closed: an interrupt, a score, a fact |

## Part — what a delta carries

`text` · `reasoning` · `tool_call` · `image` · `audio` · `video` · `file` · `custom` — read from LangChain's v1
content blocks, so the type is the same whatever the model provider.

## Views — read only what you need

A client never has to read the whole record. It declares a view — a subset of the fields, same names, same types — and
narrows any event onto it:

```python
from etrack.models.event import EventKind, EventPhase, EventView, Usage


class Cost(EventView, frozen=True, kw_only=True):
    run_id: str
    kind: EventKind
    phase: EventPhase
    usage: Usage | None = None


cost = Cost.project(event)        # every other field left behind
```

A sink declares its view once (`view: ClassVar = Cost`) and the bus narrows each event before handing it over.
→ [Sinks](sinks.md)

## Growing the record

Two ways, neither breaks a reader:

- **The `attributes` bag**, namespaced by its owner: put the run's own facts under `app.` in your LangGraph
  config's metadata and they land on the root span (→ [Tracking runs](tracking.md)).
- **A subclass**: `class MyEvent(RunEvent, frozen=True, kw_only=True): tenant: str = ""`, handed to
  `EventChannel(bus, model=MyEvent)` — every frame is validated into it.
