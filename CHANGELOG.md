# Changelog

All notable changes to e-track are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
