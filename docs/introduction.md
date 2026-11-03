# Introduction

e-track is part of the **EDamLabs eager series** (`e-`) — EDamLabs' own local-first, production-grade components
([EDamLabs families](https://github.com/edamlabs/e-workbench#identity)). e-track is its run-tracking layer.

## Why

An agent run is a tree: the run, the graph's nodes, the model calls and tool calls inside them, the subagents they
delegate to, and the subagents' own nodes and calls. When it goes wrong — or slow, or expensive — you need to see that
tree.

Every framework reports it its own way, and every place you would look at it wants it its own way: Langfuse wants its
observation types, Phoenix wants OpenInference span kinds, LangSmith its run tree, a chat UI wants the streamed text, a
dashboard the tokens. The usual answer is one integration per backend, each with its own handler hooked into the
agent, each slowing it down a little, each failing in its own way.

e-track's answer: **one record in the middle**. A source reads the framework once and writes one event per span edge;
everything else — every backend, every UI, your own code — reads that event. Adding a backend is adding a sink, never
touching the agent.

## How it works

```
your agent ──► source ──► fold ──► channel ──► bus ──┬──► otlp   → Langfuse · LangSmith · Phoenix · Tempo
 (LangGraph)   reads the   orders,   validates,      ├──► live   → the viewer, a chat, a reconnect
               callbacks   parents   publishes       └──► yours  → anything that takes events
```

| Piece | Does | You touch it |
|---|---|---|
| **Tracker** | opens a run: an id, the source's hook bound into your config | once per run: `tracker.track(...)` |
| **Source** | turns the framework's callbacks into span edges | once, when you build the tracker |
| **Fold** | orders the edges, parents them, stamps latency and the run's ids | for spans of your own code: `run.fold.span(...)` |
| **Channel** | validates each frame into a `RunEvent`, publishes it, logs a line on your logger | never, unless you emit by hand |
| **Bus** | one bounded queue and one worker per sink: publish never waits | once: `bus.subscribe(sink)` |
| **Sinks** | where the events go: OTLP, the live buffer, your own | once each |

The record is the contract: [The record](guide/record.md). The rest is wiring you do once, at startup.

## Built on open-source engines

Nothing here is reinvented; each concern runs on the tool that already does it best:

| Concern | Engine | Language |
|---|---|---|
| Reading LangGraph runs | LangChain callbacks (inline, no thread hop) | Python |
| The record and its validation | msgspec | C |
| The channel | structlog (a logger of its own) | Python |
| The bus | anyio memory streams | Python |
| Spans and logs out | OpenTelemetry SDK, OTLP/HTTP | Python |
| Encoding what agents carry | e-serde | Rust + C |
| Graph layout | rustworkx | Rust |
| The viewer's server | Litestar on granian's embedded server | Python + Rust |
| The viewer's canvas | React 19, React Flow 12 | TypeScript |

## What it is not

- **Not a tracing backend.** It stores nothing for long; it sends. The live buffer keeps the last frames of each
  conversation in memory for the viewer, nothing more. Langfuse, Phoenix or Tempo are where history lives.
- **Not a logging framework.** It never configures your logging: each frame is also one line on your own `etrack`
  logger, rendered by whatever you already set up.
- **Not tied to LangGraph by design.** LangGraph is the source that exists today; a source is one module that turns a
  framework's hooks into edges, and nothing past it knows which framework ran.
- **Not a multi-process view yet.** The viewer reads one process's live buffer: with several replicas, each viewer
  sees its own.

Next: [Installation →](installation.md)
