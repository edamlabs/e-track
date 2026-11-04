# Watch it live

The viewer draws your agent's graph and lights it as runs go through it, one conversation at a time. Install
`e-track[viewer]`.

![The viewer mid-run: the declared graph, still; the running node blazing in its family, the call it makes and the calls it made inside it; the span tree](../assets/viewer.png)

## Start it

```python
from etrack.logic.viewer import Viewer
from etrack.providers.adapters.server.granian import GranianAdapter
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter

# live: the LiveAdapter on the bus
viewer = Viewer(watch=live, topology=LanggraphTopologyAdapter().read(graph))

# a server inside your own process and event loop
async with GranianAdapter(viewer.app) as server:
    # http://127.0.0.1:28130
    print(server.url)
```

Inside a web app instead: mount `viewer.app` → [Web apps](../integrations/web.md).

## Use it

| Do | See |
|---|---|
| pick a **thread** (top bar) | every conversation the process keeps, newest first; `?thread=<id>` in the URL opens one |
| pick a **run** | the runs of that conversation, the newest by default |
| watch the **canvas** | the declared graph, drawn once and never moved: the running node blazes, the call it is making and the calls it made, counted by kind, show inside it; the arcs the run walked brighten, the last one runs |
| click a **node** | what it is: its role, the nodes it comes from and goes to, its visits in this run, the calls it made |
| click a **span** in the tree | its status, latency, tokens, reasoning, text, input and output; its node is marked on the canvas |
| click the empty canvas | clear the selection |
| read the **stream** state (top right) | `live` — following the thread · `connecting` · `reconnecting` — the stream dropped and is being retried, nothing is lost · `idle` — no thread chosen |

## Read it

| Mark | Means |
|---|---|
| border and tint | the node's nature, by family: blue model (`llm`, `embedding`) · orange action (`tool`, `mcp`, `retrieval`) · aqua delegation (`agent`, `subagent`) · yellow control (`evaluation`, `interrupt`, `state`) · grey step (a plain `node`) — the kind is always written too |
| blazing glow | running |
| white ring | the node that ran last |
| dimmed | not visited in this run |
| bright arc · running arc | walked in this run · the last one walked |
| ◌ pulsing | running |
| ✓ | done |
| ✕ red | failed — the only red on screen |
| `×3` | the node ran three times in this run |
| `llm 2 · mcp 5` | the calls the node made in this run, by kind |
| dashed arc | the arc closes a loop |

Friendlier names on the nodes → [Graphs & labels](../advanced/graphs.md).
