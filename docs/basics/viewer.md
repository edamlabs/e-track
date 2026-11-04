# Watch it live

The viewer draws your agent's graph and lights it as runs go through it, one conversation at a time. Install
`e-track[viewer]`.

![The viewer: the graph under its labels, the calls of each node beside it, the span tree, the card of a clicked node](../assets/viewer.png)

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
| watch the **canvas** | each node glows while it runs; the calls it makes — model, tools, MCP, subagents — appear beside it |
| click a **node** | what it is: its role, the nodes it comes from and goes to, its visits in this run, the calls it made |
| click a **call** or a **span** in the tree | its status, latency, tokens, reasoning, text, input and output |
| click the empty canvas | clear the selection |

## Read it

| Mark | Means |
|---|---|
| blue · orange · aqua | model (`llm`, `embedding`) · action (`tool`, `mcp`) · delegation (`agent`, `subagent`) |
| neutral | everything else — the kind is always written beside the colour |
| ◌ pulsing | running |
| ✓ | done |
| ✕ red | failed — the only red on screen |
| `×3` | the node ran three times in this run |
| dashed arc | the arc closes a loop |

Friendlier names on the nodes → [Graphs & labels](../advanced/graphs.md).
