# Changelog

All notable changes to e-track are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **The run in progress, reached from inside it** (TODO_recall 3): `etrack.logic.handle.run` — `run.span(...)` around
  any block a node, a tool or a middleware calls, with no handle passed down: `Tracker.track` binds the run's fold in a
  context variable, LangGraph carries it into its tasks, and the span hangs from what is running where it opens (the
  source locates it: `LocatePort`, met by the LangGraph source through LangChain's own context). Outside a run every
  call is a no-op; two concurrent runs never cross.
- **What a run took in and published, declared** (TODO_recall 4): `run.declare(input=…, output=…)` from the code that
  says it; the run's root END carries `input`, `output` and its `outcome` — `completed`, `interrupted` (an interrupt
  was raised in the run) or `failed`. Nothing is inferred: a run that declares no output has none, whatever model call
  came last. OTLP writes them as `input.value`/`output.value`, `gen_ai.input.messages`/`gen_ai.output.messages` and
  `etrack.outcome`. The record only grows (`VERSION` stays 1); a project's `redact` masks the declared words too
  (`RunEvent.masked`), and `Redact` moves to `etrack.models.event`.

### Fixed

- **The LangGraph source draws what ran** (TODO_recall 2): a node's `visit` is counted per mount — one subgraph
  mounted twice counts its nodes apart (breaking: `visit` values change for reused subgraphs); a subgraph compiled
  under the name of its own inner node no longer hides that node (the node is the first chain of its task, read from
  `langgraph_checkpoint_ns`); an instant frame with no coordinates (`dispatch_custom_event`) stands where its parent
  runs (`node`, `ns`, `step`); a node's END carries where it sent the run — `goto`, the destinations of the `Command`s
  it returned, beside the keys of their `update`.

### Changed

- **Settings follow the house law** (`docs/decisions.md`, 2026-11-05). One `ProviderSettings` cluster of UPPERCASE
  fields named as their variables, one `Settings` read once at import, and `infra/defaults` as the library's root.
  Every `ETRACK_*` variable is read as before; `OtlpDriver()`, `HttpDriver()` and the other providers built with no
  argument still configure themselves from the environment.
- **Overriding in code takes keyword arguments** (minor, pre-1.0): `OtlpDriver(targets={...})` replaces
  `OtlpDriver(OtlpSettings(targets={...}))`, and likewise for `HttpDriver`, `AnyioAdapter`, `LiveAdapter`,
  `GranianAdapter(app, port=…)` and `PrometheusAdapter`. The per-provider settings classes (`OtlpSettings`,
  `HttpSettings`…) are gone; their keyword arguments are typed `TypedDict`s (`OtlpConfig`, `HttpConfig`…), and
  `OtlpTarget` and `Encoding` move to `etrack.infra.config.providers`. `Secret` from `etrack.infra.config.base` is
  pydantic's `SecretStr`.
- The environment is read when e-track is first imported, no longer at a provider's first use: set `ETRACK_*` before
  the first import. Durations read ISO 8601 (`PT10S`) or `HH:MM:SS` — the docs said a bare number of seconds was
  accepted; it never was.

- The package description and keywords say what e-track is now: parallel sinks (OpenTelemetry, Langfuse, Cloud Trace,
  Prometheus, HTTP) and a live graph viewer — the same text as the repository's About on GitHub.

### Removed

- `etrack.infra.proxy.LazyProxy` and `etrack.ops.file.FileFinder`: they served only the lazy settings composer.

## [0.5.0] — 2026-11-04

### Added

- Extras, as structlog takes them: any key the record's model does not declare — a keyword to the channel, a key bound
  with `bind_contextvars` around a call or a whole run, a keyword to `run.fold.span(...)` — lands in the record's
  `attributes` and reaches every sink (OTLP span attributes, the HTTP body, the forwarded line, flat). Explicit
  `attributes` win; `EventChannel(strict=True)` refuses extras instead. Before, they were dropped silently.
- A test that sinks deliver in parallel: a slow sink never delays a fast one (each has its own worker).
- Authentication as configuration for every driver (TODO_drivers): `Auth` — `none`, `headers`, `bearer`, `basic`,
  `google` (Application Default Credentials resolved off the loop, the token refreshed off the loop when due, the
  quota project billed) — signed by one `AuthSigner`; OTLP targets take `auth`, beside their fixed headers.
- Cloud Trace through the OTLP driver: the Telemetry API (`telemetry.googleapis.com`) ingests OTLP, so a target with
  `auth: google` is all it takes — verified on the wire against a local server with stand-in credentials. There is no
  Cloud Trace emulator (the one community mock is archived and speaks Trace v2, not OTLP).
- `HttpDriver` (`e-track[http]`): events batched to any HTTP endpoint — full batch or `flush` timer, ndjson or json,
  retries with a doubling backoff on network errors, 408/425/429/5xx, signed by the configured auth — and the base of
  a custom driver: override `view`, `phases`, `accept`, `encode`, `body`. Documented with a memory service recording
  recall, and the endpoint contract such a service should expose (a TODO on the service's side).
- `PrometheusAdapter` (`e-track[prometheus]`): spans counted by kind, name and outcome, latency histograms, runs in
  flight, tokens by type and cost, in an own registry scraped from a mountable `app`; Grafana reads Prometheus, and
  Tempo or Grafana Cloud take the traces over OTLP with basic auth.

## [0.4.0] — 2026-11-04

### Changed

- Viewer canvas (TODO_canvas): the declared graph is built once and only lit — no node is ever added, dropped, moved
  or refitted while a run goes on. The calls a node makes no longer appear as nodes beside it: the running call and the
  calls made, counted by kind, show inside the node (the span tree and the node card keep every call). The running
  node blazes in its family colour, the last node to run keeps a ring, unvisited nodes recede, the arcs the run walked
  brighten and the last one runs. Borders and tints wear the family, loud from afar; a fourth family, control
  (`evaluation`, `interrupt`, `state`, yellow), joins model, action and delegation, validated as a set on the canvas
  surface (worst CVD ΔE 9.4, normal ΔE 16.8); a plain step is grey. Titles are the label alone; the technical name is
  in the node card. Frames reach React once per animation frame and fold in O(frames).
- Viewer layout fits the window: the panel is capped at a third of the width, and under 900 px it moves below the
  canvas; the bar wraps; the graph refits when its pane changes size, never while a run goes on. The stream's state
  reads `idle`, `connecting`, `live` or `reconnecting` — no longer `reconnecting` before any stream was opened.

### Fixed

- Viewer: nodes vanished mid-run. The canvas rebuilt every node object per frame without `onNodesChange`, so React
  Flow dropped their measures and hid them until a resize that never came (13 of 14 hidden, measured); the nodes now
  keep their identity for the session.

### Added

- Browser integration tests: chromium watches the canvas while a deep agent runs under it and samples every 40 ms —
  the node set constant, none hidden, the viewport never refitted, the slow node seen lit, counts, family borders,
  and the replay drawing what the live run drew; the layout on a wide and a narrow window; the viewer mounted under a
  prefix in a FastAPI and in a Litestar app; two threads run at once, each page reading its own; two runs at once on
  one thread, both offered by the run picker, each read as one run. Red on the previous canvas, green run after run.

## [0.3.0] — 2026-11-04

### Added

- Log-only tracking: `EventChannel()` takes no bus — every event validated and forwarded to the `etrack` logger,
  published nowhere; no sink, no worker to open. Hand it a bus to add the sinks; the lines keep coming.
- Node kinds: `TopologyNode.kind`, a node's nature in the spans' own vocabulary (`EventKind`: agent, tool, llm,
  evaluation, interrupt…; `NODE` by default) — declared with the node (`add_node(..., metadata={"kind": "tool"})`) or
  given by the host (`Viewer(kinds={node_id: kind})`), as labels are. A kind outside the vocabulary is refused at read.
  The canvas stripes a node in its kind's family colour and writes the kind beside it; the node card names it as its
  role.

## [0.2.1] — 2026-11-04

### Changed

- Documentation reorganised by what a reader needs (TODO_docs): Get started (what it is, install, run it in three
  steps) · Basic use (track a run, send events, watch it live) · Advanced (the record, own spans and masks, custom
  sinks, graphs and labels, logging, settings) · Integrations (LangGraph and deepagents, Langfuse, Phoenix, LangSmith,
  OpenTelemetry, web apps) · API at a glance (every public piece with its import). Code samples fit the page; every
  internal link checked.
- Tests follow the house law: a test module holds tests and file-local parametrize tables only — helpers, doubles and
  shared data moved to the conftest of their level and to `tests/support/`. What is tested is unchanged.

## [0.2.0] — 2026-11-03

### Added

- Labels: `TopologyNode.label`, the name people read on the canvas — declared with the node
  (`add_node(..., metadata={"label": …})`) or given by the host (`Viewer(labels={node_id: label})`); the node's `name`,
  which its spans carry, is untouched.
- Viewer: clicking any node of the graph opens its card — role, name, the arcs in and out (routers and loops marked),
  every visit of the run and the calls it made, each one clicked open. Kinds are coloured by family (model, action,
  delegation — three hues, validated together for colour-blind readers), and the kind is always written beside its
  colour; status is a glyph (◌ ✓ ✕), never a kind's hue. A legend in the top bar.
- An end-to-end test of the viewer: a deep agent watched through granian on a real port — topology with labels, the
  thread list, one SSE stream replaying a run and following the next, every offset once and in order.

### Fixed

- Viewer: the canvas refits as it grows, once its nodes are measured — the calls a run makes no longer fall outside the
  first frame, nor does the first fit land off-centre.
- Layout keeps whatever a node or an arc carries beyond its place (it rebuilt them field by field).
- `make docs` is the strict build, as the fleet's docs module expects (it was the live server, which never ends: the
  fleet run timed out and never reached its release); `make docs-serve` serves.

### Changed

- Documentation rewritten (TODO_docs): what e-track is for and how to use it — introduction, installation, a
  three-step quickstart, and a guide (the record, tracking runs, sinks, backends, viewer, logging, settings), every
  example run for real with its output; the README follows.

## [0.1.3] — 2026-11-03

### Added

- Viewer (`e-track[viewer]`, TODO_viewer): the declared graph and every thread's span tree, live. `Viewer(watch,
  topology)` places the graph and builds an ASGI app — `/api/topology`, `/api/threads`, `/api/threads/{thread}/events`
  (Server-Sent Events, resumed by `Last-Event-ID`), OpenAPI, and a React Flow canvas shipped in the wheel —
  mountable in a host or served by `GranianAdapter`, granian's embedded server inside the host's loop.
- `LiveAdapter.threads()`: the kept threads, newest first, with their runs. `WatchPort`, `LiveFrame`, `LiveSummary`
  and `ServerPort` join the ports.
- `LanggraphTopologyAdapter.read` takes the JSON of LangChain's `Graph.to_json()` as well as a compiled graph.
- `LanggraphSourceAdapter` lifts the run's metadata under `app.` (agent versions, tenant…) onto the root span's
  `attributes`: every sink sees the run's own facts — OTLP exports them as span attributes.

### Fixed

- Bus: `health()` is false once the supervisor ends, and a supervisor that fails before opening raises instead of
  hanging `__aenter__` (its streams closed).

### Changed

- The integration sandbox moves to `tests/sandbox/`, a test resource beside the fixtures that bring it up.

## [0.1.2] — 2026-11-03

### Fixed

- `OtlpDriver` exports usage as mutually exclusive buckets (`langfuse.observation.usage_details`: input and output
  without their cached and reasoning parts, `input_cache_read`, `input_cache_creation`, `output_reasoning`) and the
  GenAI detail counters. Before, Langfuse priced cached input at the full input rate: measured on deeptrack's tracing
  A/B, up to 2× the native handler's cost on the same tokens.

## [0.1.1] — 2026-11-03

### Fixed

- `AnyioAdapter` no longer ties its task group to the task that opened it: a supervisor task owns the group, so the bus
  can be entered and left by different tasks (async-generator fixtures, split lifespans) without anyio's "exit cancel
  scope in a different task". `subscribe` after open is now safe from a foreign thread (hops onto the loop).

## [0.1.0] — 2026-11-03

### Added

- `RunEvent` v1: one record per span edge — `kind` (13, `CUSTOM` fallback) × `phase` (start, delta, end, error,
  instant) × `part` (text, reasoning, tool call, media, custom); typed `model`/`usage`/`error` sections, an open
  `attributes` bag, subclassable; `EventView` narrows it per client.
- `EventChannel`: the log as the bus — reserved keys validated, published, forwarded to the host's `etrack` logger.
- `Tracker.track`: one run from a host config — uuid7 run id pinned as LangChain's root, contextvars bound.
- `FoldProcessor`: edges → ordered, parented frames (`seq`, `visit`, latency, redaction, own spans and instants).
- Providers: `AnyioAdapter` (bounded per-sink fan-out, thread-safe publish, drop and failure counters),
  `LanggraphSourceAdapter` (callbacks inline: run, node, LLM, tool, MCP, subagent, retriever, interrupt, custom; v1
  content blocks), `LanggraphTopologyAdapter`, `LiveAdapter` (per-thread replay by offset), `OtlpDriver` (spans and
  logs with derived W3C ids; GenAI, OpenInference and Langfuse attributes; host log processor).
- `LayoutProcessor`: ranks, lanes and loops of a declared graph (rustworkx).
- Integration tier on real services: `sandbox/compose.yml` (OpenTelemetry Collector + Arize Phoenix) brought up and
  down by pytest-docker session fixtures, ephemeral ports, per-session output. A deep agent (subagent + MCP tool) runs
  through every layer; the collector proves the span tree and the logs, Phoenix the OpenInference kinds.
- Published on PyPI as `e-track` (TODO_pypi): EDamLabs identity (`[tool.edamlabs]` lib/eager), `py.typed`, a tag-driven
  release (wheel smoke, build provenance, trusted publishing), digest-pinned CI (static gates, unit matrix on three
  OSes, integration, docs on Pages), Renovate, the fleet's maintenance contract, house wordmark and Zensical site.

### Changed

- Providers are named brand then nature: `AnyioBusAdapter` → `AnyioAdapter`, `LiveSinkAdapter` → `LiveAdapter`;
  `test_taxonomy` gates the law.
- `beartype` leaves the dependencies: nothing imports it.

### Fixed

- The OTLP driver encodes attribute values with e-serde: pydantic messages, dataclass commands, structs and dates
  canonicalized, unknown objects as text. Found by the e2e run: a `ToolMessage` output made the OTLP sink fail.
  Serialization is each sink's own concern; the record carries what the source saw.
