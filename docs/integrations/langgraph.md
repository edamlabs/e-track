# LangGraph and deepagents

`LanggraphSourceAdapter` reads any LangGraph run — plain `StateGraph`s, compiled subgraphs, deep agents with their
subagents — through LangChain's callbacks: inline, on the caller's thread, no queue, no thread hop. The graph is never
wrapped or rebuilt; it only gets a config with one more callback. Install `e-track[langgraph]`.

```python
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter

source = LanggraphSourceAdapter(mcp=frozenset({"onto_query", "web_search"}))
tracker = Tracker(EventChannel(bus), source)

with tracker.track(thread="t1", config={"configurable": {"thread_id": "t1"}}) as run:
    await agent.ainvoke({"messages": [("user", "…")]}, run.config)
```

| kwarg | type | default | |
|---|---|---|---|
| `mcp` | `frozenset[str]` | `∅` | tool names served over MCP: their spans are `mcp`, not `tool` |
| `subagents` | `frozenset[str]` | `{"task"}` | tools that delegate to a subagent — deepagents' `task`; the span is named by its `subagent_type` |

## What becomes what

| LangGraph / LangChain sees | Event `kind` |
|---|---|
| the root chain | `run` |
| a chain named after its own `langgraph_node` | `node` — a compiled subgraph mounted as a node is one span, not two |
| a chat model or LLM | `llm`, with `delta`s typed by LangChain's v1 content blocks (text, reasoning, tool-call arguments, media) |
| a tool · a tool in `mcp` · the `task` tool | `tool` · `mcp` · `subagent` |
| a retriever | `retrieval` |
| a `GraphInterrupt` | one `interrupt` instant, under the span that raised it, carrying what is asked |
| `dispatch_custom_event(name, data)` from a node or a tool | a `custom` instant under the span that dispatched it |
| sequences, middleware wrappers, other plumbing | folded away: a frame's parent is always a span that was emitted |

Model calls carry `model` (provider, name, temperature, max tokens) and, on `end`, `usage` (input, output, reasoning,
cache read and write tokens) as LangChain reports them.

## One id for the run

The source pins the run's id as LangChain's root run id. LangSmith, Langfuse, Phoenix, your logs and the viewer all
name the run the same — search one id anywhere.

## The run's own facts

Put a run's facts under `app.` in the config's metadata — agent version, tenant, experiment arm — and they land on
the root span's `attributes`, so every backend shows them:

```python
config = {"metadata": {"app.tenant": "acme", "app.agent_version": "2026.11.3"}}
with tracker.track(thread="t1", config=config) as run:
    ...
```

The root `run` event then carries `attributes={'app.tenant': 'acme', 'app.agent_version': '2026.11.3'}`; every key
under `app.` is lifted, nothing else of the metadata is.

## Callbacks you already have

Your config's callbacks — a list or a callback manager, LangSmith's tracer, Langfuse's handler — are kept; e-track's
handler is added beside them. A callbacks value of any other shape raises `SourceError`.

## The declared graph

The same compiled graph gives the viewer its map → [Graphs & labels](../advanced/graphs.md):

```python
# nodes and arcs as declared, deep agent nodes included
topology = LanggraphTopologyAdapter().read(agent)
```
