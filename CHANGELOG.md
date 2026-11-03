# Changelog

All notable changes to e-track are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
