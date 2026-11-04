# Graphs, labels and kinds

The viewer draws the graph your system **declares** — read once at startup — and lights it with what each run
**does**. This page is the declared side: where a graph comes from, how its nodes are named for people, and what the
viewer serves.

## Where a graph comes from

Everything becomes a `Topology` — nodes and arcs — which the viewer lays out on a grid (rank by step from the entry,
lane by neighbours, loops marked):

```python
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter

# a) a compiled LangGraph graph — deep agents and compiled subgraphs opened into nodes
topology = LanggraphTopologyAdapter().read(compiled_graph)

# b) the JSON LangChain exports — a graph you have as a file or from another process
exported = compiled_graph.get_graph(xray=True).to_json()
topology = LanggraphTopologyAdapter().read(exported)

# c) by hand — any system, any framework
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode

topology = Topology(
    nodes=(
        TopologyNode(id="plan", name="plan", label="Plan", entry=True),
        TopologyNode(id="act", name="act"),
    ),
    edges=(TopologyEdge(id="plan>act", source="plan", target="act"),),
)
```

| `TopologyNode` | |
|---|---|
| `id` | the node's id in the graph |
| `name` | what its spans carry: a `node` span named `plan` lights the node named `plan` |
| `label` | what people read; empty → the name |
| `kind` | what the node is — an `EventKind` (`agent`, `tool`, `llm`, `evaluation`, `interrupt`…); `node`, a plain step, by default |
| `entry`, `exit` | where a run enters and leaves |

| `TopologyEdge` | |
|---|---|
| `source`, `target` | the node ids it joins |
| `conditional`, `label` | a router chooses it, and the branch it is |

A subagent launched through a tool is not declared anywhere: it is counted inside the node that launched it, and
shown whole in the span tree.

## Labels — names for people

A node's `name` is what its spans carry: `PatchToolCallsMiddleware.before_agent`, `tools`. It ties the node to its
spans and never changes. A **label** is what the canvas shows instead — one word reads best from afar; the name stays
in the node's card and its tooltip. Two ways to give one:

=== "Where the node is declared"

    ```python
    graph.add_node("plan", plan, metadata={"label": "Plan the answer"})
    ```

    LangGraph keeps node metadata in the compiled graph and in `Graph.to_json()`: the topology adapter reads `label`
    from either.

=== "For a graph you did not declare"

    ```python
    viewer = Viewer(
        watch=live,
        topology=topology,
        labels={
            "PatchToolCallsMiddleware.before_agent": "Patch tool calls",
            "_ParentNotifierMiddleware.after_agent": "Notify parent",
        },
    )
    ```

    By node id, over any declared label — for a library's middleware, a deep agent's own nodes, a mounted subgraph.

The span tree shows the same labels for node spans.

## Kinds — what a node is

A node's **kind** is its nature in the spans' own vocabulary, and its colour on the canvas: the border and the tint
wear its family, and the kind is written on the node.

| Family | Kinds | Colour |
|---|---|---|
| model | `llm`, `embedding` | blue |
| action | `tool`, `mcp`, `retrieval` | orange |
| delegation | `agent`, `subagent` | aqua |
| control | `evaluation`, `interrupt`, `state` | yellow |
| step | `node`, everything else | grey |

The same two doors as labels:

```python
graph.add_node("gate", gate, metadata={"label": "Gate", "kind": "evaluation"})

viewer = Viewer(watch=live, topology=topology, kinds={"model": EventKind.LLM, "tools": EventKind.TOOL})
```

A kind outside `EventKind` is refused when the graph is read.

## `Viewer`

| kwarg | type | |
|---|---|---|
| `watch` | `WatchPort` — `LiveAdapter` | where the frames are read |
| `topology` | `Topology` | the declared graph; the viewer lays it out once |
| `labels` | `Mapping[str, str]` | node id → the label people read; over any declared label |
| `kinds` | `Mapping[str, EventKind]` | node id → what the node is; over any declared kind |

| Attribute | |
|---|---|
| `app` | the ASGI app |
| `topology` | the graph as laid out: every node's `rank`, `lane`, `label` and `kind`, the arcs that close a loop marked |

`LanggraphTopologyAdapter().read(...)` takes a compiled LangGraph graph — deep agents included, subgraphs opened — or
the JSON of LangChain's `graph.get_graph().to_json()`, for a graph you only have as a file or from another process.

## Lay out without the viewer

```python
from etrack.processors.layout import LayoutProcessor

# every node's rank and lane, loops marked; needs e-track[topology]
placed = LayoutProcessor().place(topology)
```

## The viewer's API

The canvas is a client of a small API, open to yours:

| Door | |
|---|---|
| `GET /api/topology` | the laid-out graph |
| `GET /api/threads` | the kept conversations, newest first: `thread`, `offset`, `runs`, `last` |
| `GET /api/threads/{thread}/events` | Server-Sent Events, one `frame` message per event: `id` is the frame's offset in the thread, `data` the `RunEvent` as JSON. It replays what is kept, then follows live; resume with `?after=<offset>` — a browser's `EventSource` resumes by itself through `Last-Event-ID` |
| `GET /api/schema` | OpenAPI |

```bash
curl -N http://127.0.0.1:28130/api/threads/t1/events?after=41
```

```text title="one message, its data abridged"
id: 42
event: frame
data: {"v":1,"run_id":"01a1a226…","thread_id":"t1","seq":3,"kind":"node","phase":"start","name":"tools",…}
```

## Viewer settings

| setting | default | |
|---|---|---|
| `ETRACK_SERVER_HOST` | `127.0.0.1` | loopback by default: frames carry prompts and tool outputs |
| `ETRACK_SERVER_PORT` | `28130` | |
| `ETRACK_SERVER_BOOT` | `10s` | how long opening waits for the socket to answer |

!!! warning "What it shows is what your agent saw"
    Inputs, outputs and reasoning travel to the browser as they are, after your `redact`. Keep it on loopback, or
    behind your app's own authentication when mounted.

The viewer reads one process's live buffer: with several replicas, each viewer sees its own conversations.
