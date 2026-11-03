# Viewer

A live canvas of your agent: its graph as declared, lit while a run goes through it, with a picker for every
conversation the process keeps. Install `e-track[viewer]`.

![The viewer: thread and run pickers and the colour legend on top; the graph under its labels, the calls of each node beside it in their family colours; the span tree, and the card of the clicked node — its wiring, visits and calls](../assets/viewer.png)

| Where | What you see |
|---|---|
| **Top bar** | the thread picker (every conversation kept, newest first, with its frame count), the run picker within it (the newest run by default), the colour legend, and the stream's state — `live` or `reconnecting` |
| **Canvas** | the declared graph laid out by rank and lane, each node under its label; the calls a node made — model, tools, MCP, subagents — appear beside it as they happen; dashed arcs close loops |
| **Span tree** | the whole run as a tree, subagents' graphs nested in place, each span with its status and latency |
| **Detail** | whatever you clicked — a node, a call, a span (below) |

**Click anything.** Every element answers what it is:

| Click | Shows |
|---|---|
| a **node** of the graph | its label and the `name` its spans carry, its role (entry, exit, node), the nodes it comes from and goes to — router branches and loops marked —, each of its visits in this run with its status and latency, and the calls it made; each visit and call opens on click |
| a **call** beside a node | the span: kind, status, latency, tokens, error, reasoning and text, input and output |
| a **span** in the tree | the same, for any span, subagents' included |
| the empty canvas | clears the selection |

**Colours are families, status is a shape.** Kinds are coloured by what they do, and the kind is always written beside
its colour; status never borrows a kind's hue:

| Colour | Family | Kinds |
|---|---|---|
| blue | model | `llm`, `embedding` |
| orange | action | `tool`, `mcp` |
| green-aqua | delegation | `agent`, `subagent` |
| neutral | structure and facts | `run`, `node`, `retrieval`, `interrupt`, `state`, `evaluation`, `custom` |

| Glyph | Status |
|---|---|
| ◌ (pulsing) | running |
| ✓ | done |
| ✕ (red, the only red on the canvas) | error |

Three hue families is a measured limit, not a taste: on the dark canvas, with every pair on screen at once, a fourth
hue falls below the distance colour-blind readers can tell apart, and past four no reader can.

The canvas lights the outer graph only: a subagent runs its own graph, shown inside its span in the tree.

## Serve it

```python
from etrack.logic.viewer import Viewer
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter

topology = LanggraphTopologyAdapter().read(graph)        # read the graph once, at startup
viewer = Viewer(watch=live, topology=topology)           # live: the LiveAdapter subscribed to the bus

async with GranianAdapter(viewer.app) as server:         # granian's embedded server, in your own event loop
    print(server.url)                                    # http://127.0.0.1:28130
```

`GranianAdapter` runs granian's Rust server as a task of your process's own loop — no second process, no thread of
yours, no signal handler taken from you. It refuses a port already taken and raises `ServerError` if the socket does
not answer within `ETRACK_SERVER_BOOT`.

## Or mount it in your app

`viewer.app` is a plain ASGI app: mount it under any prefix; the canvas uses relative paths.

=== "Litestar"

    ```python
    from litestar import Litestar, asgi

    app = Litestar(route_handlers=[..., asgi("/etrack", is_mount=True, copy_scope=True)(viewer.app)])
    ```

=== "FastAPI · Starlette"

    ```python
    app.mount("/etrack", viewer.app)
    ```

Link a conversation straight to its canvas: `/etrack/?thread=<thread_id>`.

## Labels — names for people

A node's `name` is what its spans carry: `PatchToolCallsMiddleware.before_agent`, `tools`. It ties the node to its
spans and never changes. A **label** is what the canvas shows instead — the name stays visible beneath it, and in the
node's card. Two ways to give one:

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

## `Viewer`

| kwarg | type | |
|---|---|---|
| `watch` | `WatchPort` — `LiveAdapter` | where the frames are read |
| `topology` | `Topology` | the declared graph; the viewer lays it out once |
| `labels` | `Mapping[str, str]` | node id → the label people read; over any declared label |

| Attribute | |
|---|---|
| `app` | the ASGI app |
| `topology` | the graph as laid out: every node's `rank`, `lane` and `label`, the arcs that close a loop marked |

`LanggraphTopologyAdapter().read(...)` takes a compiled LangGraph graph — deep agents included, subgraphs opened — or
the JSON of LangChain's `graph.get_graph().to_json()`, for a graph you only have as a file or from another process.

## The API

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

## Settings

| setting | default | |
|---|---|---|
| `ETRACK_SERVER_HOST` | `127.0.0.1` | loopback by default: frames carry prompts and tool outputs |
| `ETRACK_SERVER_PORT` | `28130` | |
| `ETRACK_SERVER_BOOT` | `10s` | how long opening waits for the socket to answer |

!!! warning "What it shows is what your agent saw"
    Inputs, outputs and reasoning travel to the browser as they are, after your `redact`. Keep it on loopback, or
    behind your app's own authentication when mounted.

The viewer reads one process's live buffer: with several replicas, each viewer sees its own conversations.
