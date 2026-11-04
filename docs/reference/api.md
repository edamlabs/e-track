# API at a glance

Every public piece, by what it is for, with the line that imports it. Signatures and docstrings in full: the
generated reference under **Reference** in the navigation.

## Track

| | Import | |
|---|---|---|
| `Tracker` | `from etrack.logic.api import Tracker` | opens runs: `tracker.track(thread, config, run_id=None)` → [Track a run](../basics/tracking.md) |
| `EventChannel` | `from etrack.logic.channel import EventChannel` | validates, publishes and logs every frame; `emit(event)`, `log.info("run.event", …)` |
| `FoldProcessor` | reached as `run.fold` | spans and facts of your own code: `span(...)`, `instant(...)` → [Own spans](../advanced/spans.md) |
| `LanggraphSourceAdapter` | `from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter` | reads LangGraph runs → [LangGraph](../integrations/langgraph.md) |

## Carry and deliver

| | Import | |
|---|---|---|
| `AnyioAdapter` | `from etrack.providers.adapters.bus.anyio import AnyioAdapter` | the bus: `subscribe(sink, select=None)`, `dropped`, `failed` → [Send events](../basics/events.md) |
| `LiveAdapter` | `from etrack.providers.adapters.sink.live import LiveAdapter` | the live buffer: `watch(thread, after)`, `threads()`, `offset(thread)` |
| `OtlpDriver` | `from etrack.providers.drivers.sink.otlp import OtlpDriver` | OpenTelemetry spans and logs: `flush()`, `processor()` → [OpenTelemetry](../integrations/opentelemetry.md) |

## Watch

| | Import | |
|---|---|---|
| `Viewer` | `from etrack.logic.viewer import Viewer` | the live canvas: `Viewer(watch, topology, labels={})`, `.app`, `.topology` → [Watch it live](../basics/viewer.md) |
| `GranianAdapter` | `from etrack.providers.adapters.server.granian import GranianAdapter` | serves an ASGI app in your loop: `.url` → [Web apps](../integrations/web.md) |
| `LanggraphTopologyAdapter` | `from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter` | `read(graph or Graph.to_json())` → `Topology` → [Graphs & labels](../advanced/graphs.md) |
| `LayoutProcessor` | `from etrack.processors.layout import LayoutProcessor` | `place(topology)`: rank, lane, loops |

## The record and its values

| | Import | |
|---|---|---|
| `RunEvent` | `from etrack.models.event import RunEvent` | one frame of a run → [The record](../advanced/record.md) |
| `EventKind`, `EventPhase`, `Part` | `from etrack.models.event import EventKind, EventPhase, Part` | what a span is, where it is in its life, what a delta carries |
| `Usage`, `ModelRef`, `Failure`, `RunScope` | `from etrack.models.event import Usage, ModelRef, Failure, RunScope` | typed sections of a frame; a run's ids |
| `EventView`, `LogView` | `from etrack.models.event import EventView, LogView` | narrow a frame to the fields a client reads |
| `Edge` | `from etrack.ports.source import Edge` | a span as you report it to `run.fold.instant` |
| `Topology`, `TopologyNode`, `TopologyEdge` | `from etrack.ports.topology import Topology, TopologyNode, TopologyEdge` | a declared graph |
| `LiveFrame`, `LiveSummary` | `from etrack.ports.sink import LiveFrame, LiveSummary` | a watched frame with its offset; a kept thread |

## Contracts — to write your own

| | Import | Meet it to write |
|---|---|---|
| `SinkPort` | `from etrack.ports.sink import SinkPort` | a sink → [Custom sinks](../advanced/sinks.md) |
| `WatchPort` | `from etrack.ports.sink import WatchPort` | a live store the viewer can read |
| `SourcePort`, `FoldPort` | `from etrack.ports.source import SourcePort, FoldPort` | a source for another framework |
| `TopologyPort` | `from etrack.ports.topology import TopologyPort` | a graph reader for another framework |
| `ServerPort` | `from etrack.ports.server import ServerPort` | another embedded server |
| `Provider`, `ProviderSpec` | `from etrack.ports.provider import Provider, ProviderSpec` | the lifecycle every provider shares: `async with`, `health()`, `spec` |

## Settings and errors

| | Import |
|---|---|
| `AnyioSettings` | `from etrack.infra.config.providers.adapters.bus.anyio import AnyioSettings` |
| `LiveSettings` | `from etrack.infra.config.providers.adapters.sink.live import LiveSettings` |
| `OtlpSettings`, `OtlpTarget` | `from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget` |
| `GranianSettings` | `from etrack.infra.config.providers.adapters.server.granian import GranianSettings` |
| `CoreError` and its family | `from etrack.infra.errors import CoreError, ChannelError, BusError, SinkError, SourceError, ServerError, LayoutError` |

Every variable each setting reads → [Settings](../advanced/settings.md).
