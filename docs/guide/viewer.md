# Viewer

A live canvas of your agent: its graph as declared, lit while a run goes through it, with a picker for every
conversation the process keeps. Install `e-track[viewer]`.

![The viewer: thread and run pickers on top; the graph lit by the run, the calls of each node beside it; the span tree and the selected span's input and output on the right](../assets/viewer.png)

| Where | What you see |
|---|---|
| **Top bar** | the thread picker (every conversation kept, newest first, with its frame count), the run picker within it (the newest run by default), and the stream's state — `live` or `reconnecting` |
| **Canvas** | the declared graph laid out by rank and lane; a node glows while its span runs, turns green when it ends, red when it fails, and counts its visits (`×2`); the calls a node made — model, tools, MCP, subagents — appear beside it as they happen; dashed arcs close loops |
| **Span tree** | the whole run as a tree, subagents' graphs nested in place, each span with its latency |
| **Detail** | the selected span: status, latency, tokens, error, reasoning and text, input and output |

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

## `Viewer`

| kwarg | type | |
|---|---|---|
| `watch` | `WatchPort` — `LiveAdapter` | where the frames are read |
| `topology` | `Topology` | the declared graph; the viewer lays it out once |

| Attribute | |
|---|---|
| `app` | the ASGI app |
| `topology` | the graph as laid out: every node's `rank` and `lane`, the arcs that close a loop marked |

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
