# Decisions

### 2026-11-03 · Run tracking is its own library, and the log is its bus

**Decision.** Event tracking for agent runs is e-track: one `RunEvent` model whose field names are the reserved
keys of a structlog channel of its own; the channel validates, publishes on a bounded per-sink bus and forwards a
narrowed line to the host's logger. Frameworks enter through sources (LangGraph callbacks today), clients through
sinks that declare a partial view (OTLP for Langfuse, LangSmith, Phoenix and any collector; live replay for a
canvas). Its spine lives inside the package (`etrack.infra`, …), not at `src/` root.

**Evidence.** Callbacks see every span with ids for free; LangGraph's InstrumentGraph cannot instrument a graph it did
not build. A top-level `infra` package would merge with the consumer's in site-packages. Measured: one emission costs
the producer p50 4.8 µs, p99 8.5 µs (2 000 frames, bus + sink, no forwarding).

**Rejected.** An event bus with the logger as one more sink (two models to keep aligned); the host's logger as the
bus (its level filter would drop events); extending InstrumentGraph; native Langfuse/LangSmith handlers as the
primary path.

### 2026-11-03 · Out of the workbench, onto PyPI, under EDamLabs

**Decision.** `e-workbench/labs/etrack` moves to `edamlabs/e-track` and is published as `e-track` (import name
`etrack`). `pyproject.toml` declares `[tool.edamlabs]` `kind = "lib"`, `family = "eager"`; the fleet entry
`e-workbench/fleet/e-track.toml` repeats it and runs `deps`, `security`, `drift`, `release`, `docs`, `community`.

**Evidence.** A lab cannot be depended on by version; deeptrack and any other host need a release. e-serde set the
EDamLabs shape: Renovate, a digest-pinned CI, Zensical docs on Pages, the fleet as maintenance engine.

**Rejected.** `e_track` as import name — the naming law's default — since the eager series already ships `eserde`
for `e-serde` and deeptrack imports `etrack`; renaming buys consistency with a law the series does not follow.

### 2026-11-03 · The tag is the version; the fleet cuts it

**Decision.** `uv-dynamic-versioning` reads the version from the `v*` tag. `release.yml` runs on the tag: build, a
smoke import of the wheel in a clean env, the artifacts checked against the tag, build provenance, PyPI through
trusted publishing (inert until `PUBLISH_PYPI=true`), then the GitHub release with the CHANGELOG section as notes.
The fleet's `release` module folds `[Unreleased]`, merges the release PR and pushes the tag; the first tag is a
human's.

**Evidence.** The fleet's release stage skips manifests with a dynamic version and leaves publishing to the
repository's tag-driven workflow. A tag-less checkout builds `0.0.0`: the jobs fetch the full history.

**Rejected.** e-serde's dispatch-driven bump (it carries a static Cargo version the fleet must edit; e-track has
none); publishing on merge (a merge is not a release).

### 2026-11-03 · A namespace package with `py.typed`, no `__init__.py`

**Decision.** `src/etrack` stays a PEP 420 namespace package; `py.typed` marks it typed.

**Evidence.** A consumer with the wheel installed type-checks against it: mypy, pyright and ty all report the
deliberate errors in `RunEvent` and `FoldProcessor` usage — the marker is read without an `__init__.py`.

**Rejected.** A root `__init__.py` (e-serde keeps one): no tool needs it, and the public surface is `etrack.logic.api`.

### 2026-11-03 · The integration sandbox is a session fixture

**Decision.** `tests/sandbox/compose.yml` (a test resource, beside the fixtures that use it) — an OpenTelemetry Collector (contrib 0.162.0) writing OTLP/JSON files, and
Arize Phoenix (21.0.0) — is brought up by pytest-docker when the first integration test asks for it and torn down
when the session ends. Host ports are ephemeral, the collector's output is a per-session temp dir, the tier is
opt-in (`-m integration`) and errors without docker instead of skipping. Unit tests keep faking every outbound
service in process; coverage stays gated at 100 %.

**Evidence.** The collector proves the wire (span tree and log records by trace id); Phoenix proves the dialect — its
REST API returns the OpenInference kinds it read (`AGENT` for a subagent, `TOOL`, `LLM`). Phoenix 21 authenticates
OTLP by default (401 on first run): the sandbox disables it, header auth is unit-tested.

**Rejected.** `make stack` before the tests and a skip when nothing answers (a silent skip hides a missing tier);
testcontainers (a heavier client for the same compose lifecycle); Langfuse in the sandbox (six containers);
Jaeger (traces only, logs unverifiable).

### 2026-11-03 · Providers are named brand, then nature

**Decision.** `AnyioBusAdapter` → `AnyioAdapter`, `LiveSinkAdapter` → `LiveAdapter`; the capability enters the name
only when a brand repeats across capabilities (`LanggraphSourceAdapter`, `LanggraphTopologyAdapter`).
`test_taxonomy_provider_name_is_brand_then_nature` holds it.

**Evidence.** The naming law: a brand module inside a layer takes the layer as surname (`PsqlpyDriver`), a repeated
brand takes its capability as qualifier (`TeiEmbedDriver`). `OtlpDriver` already followed it; two adapters did not.

**Rejected.** Keeping the capability everywhere (the folder already says it; the law forbids saying it twice).

### 2026-11-03 · The live viewer ships in e-track, on Litestar and granian

**Decision.** The viewer deeptrack was building (TODO_viewer, transferred) is `e-track[viewer]`: a Litestar app
(`etrack.api.viewer`) over the live sink's `WatchPort` and a laid-out `Topology`, served by granian's embedded server
as a task of the host's loop (`GranianAdapter`) or mounted in the host's own app; the canvas (Vite, React 19,
`@xyflow/react` 12) is built into `etrack/ui/dist` and shipped in the wheel and the sdist. The stream is Server-Sent
Events — `id` = the thread offset, resumed by `Last-Event-ID` — and its frames are encoded by e-serde. The canvas's
TypeScript types are generated from msgspec's JSON Schema of the API (`make ui-types`), drift-gated.

**Evidence.** The record, the topology, the layout and the live buffer already lived here; deeptrack's track API was
generic glue. granian embedded: up in 24–64 ms, clean stop, no signal handler taken. A real deep-agent run, viewed in a
browser, found two defects the unit tier had missed: LangChain objects in payloads killed the stream (e-serde 0.6.4
fixed its Struct walk) and a subagent's inner nodes lit the outer graph's (the canvas now lights only the outer run).

**Rejected.** uvicorn (granian is the house's Rust-backed server and embeds); AG-UI as the stream (a chat protocol, not
a span tree); client-side layout (ELK — the server places the graph once); WebSocket (one-way, resumable SSE suffices);
an in-memory ASGI test transport for SSE (it buffers the whole response — the SSE tests run on a real granian port).

### 2026-11-03 · A node's label is not its name; kinds take three colour families

**Decision.** `TopologyNode` gains `label`, display only, beside `name` — declared with the node in LangGraph's
metadata or given by the host (`Viewer(labels=…)`). Kinds are coloured by family on the canvas — model (blue), action
(orange), delegation (aqua) — every other kind neutral, the kind always written beside its colour; status is a glyph
(◌ ✓ ✕), red only for an error.

**Evidence.** `name` is the key a span lights its node with: renaming it would unlink the canvas from the run. The
palette was validated with the dataviz checker on the canvas surface, every pair on screen: a fourth hue drops the
colour-blind separation to ΔE 1.6 (deutan), a fifth breaks the normal-vision floor; the status green and red clashed
with the orange and aqua at any count, so status left hue for shape.

**Rejected.** An alias on `RunEvent` (the record would carry presentation); one hue per kind (thirteen hues no reader
tells apart); status as border colour (it collided with the kinds).

### 2026-11-04 · The canvas is the declared graph, lit; kinds take four families

**Decision.** The canvas draws the declared graph once per topology and never adds, drops, moves or refits a node: a
run only lights it — the running node blazes in its family, the last one keeps a ring, unvisited nodes recede, walked
arcs brighten. The calls a node makes are counted inside it, no longer drawn beside it. A fourth colour family,
control (`evaluation`, `interrupt`, `state`), yellow `#d4a000`, joins model, action and delegation; a plain step is grey.
Supersedes the three-family half of 2026-11-03.

**Evidence.** Measured in chromium on a deep agent's run: the old canvas hid 13 of 14 nodes mid-run (node objects
rebuilt per frame, measures dropped by React Flow v12) and refitted the view as call nodes came and went. The browser
tests now pin the node set, zero hidden nodes and one viewport across the whole run; red on the old canvas, green five
runs in a row. Palette, dataviz checker on `#0b1522`, all pairs: violet failed protan (ΔE 1.9 with blue), magenta
deutan (1.6 with aqua) and the normal floor (11.6 with orange), dark yellow `#c98500` the normal floor (10.6);
`#d4a000` passes CVD (worst 9.4) and normal vision (16.8), above the lightness band — accepted: it is a border read
from afar, and the kind is always written beside it.

**Rejected.** Keeping call nodes and only fixing the measures (the graph still reshaped with every call); a refit
per growth (the view jumped under the reader); a fourth hue from the violet or magenta steps (failed CVD).

### 2026-11-04 · Auth is configuration every driver shares; Cloud Trace is an OTLP target; custom sinks build on HTTP

**Decision.** Authentication is one `Auth` value in a driver's configuration, signed by one `AuthSigner`; Google is a
kind of auth, not a driver: Cloud Trace is an OTLP target with `auth: google`. A custom sink is a subclass of
`HttpDriver`, which owns batching, timing, signing and retries; Prometheus is an in-process adapter scraped from an app.

**Evidence.** Google's Telemetry API ingests OTLP at `telemetry.googleapis.com` (docs, 2026-11-04); the OTLP HTTP
exporter takes a `requests.Session`, and google-auth's `AuthorizedSession` is one that refreshes its token and retries a
401 — checked in code. The bus already gives every sink a worker, a bounded queue and a `select`: the HTTP driver adds
only what a remote system needs. Tests: the signer for every kind and for Google's refresh, the OTLP Google target and
a bearer target on the wire, the HTTP driver against a real local server (batch, timer, retries, refusals, an
unreachable host, a subclass), Prometheus' samples and its scrape, and a deep agent's run end to end through the bus
into both; coverage 100 %.

**Rejected.** A Cloud Trace v2 (gRPC `BatchWriteSpans`) driver — OTLP reaches the same store with the driver we have;
googleinterns/cloud-operations-api-mock as a local fake — archived since 2022, Trace v2 only; a queue and worker inside
the HTTP driver — the bus already isolates every sink; Pushgateway — Prometheus scrapes, and pushed traces go over
OTLP. Not measured: a Rust-backed HTTP client (wreq, rnet) against httpx for this driver — open for a benchmark.

### 2026-11-05 · Settings: one cluster of UPPERCASE fields; `infra/defaults` is the library's root

**Decision.** The house settings law (e-nous `proj-py-layout/references/settings.md`, library case): one
`ProviderSettings` cluster in `infra/config/providers.py` whose fields are the env variables themselves
(`ETRACK_OTLP_TARGETS`, no `env_prefix`), strictly typed; `Settings` inherits it and is read once, at import. Every
provider takes keyword arguments — `OtlpDriver(targets=…)`, typed by a `TypedDict` (`OtlpConfig`…) and validated by its
`TypeAdapter` — and never reads `st`. `infra/defaults` is the composition root a library lacks: the only module that
reads `st`, it fills what a provider is not handed, so `OtlpDriver()` still reads `ETRACK_OTLP_*`.

**Evidence.** Every env name of 0.5.0 held: the 27 in `tests/resources/settings/env.json`, taken from main before the
change. Gates in `tests/unit/etrack/infra/test_settings.py`: uppercase, no field in two clusters, the snapshot, root-only
reads (mutation-checked: an `infra.settings` import in `LiveAdapter` fails it), types only below the root.

**Rejected.** The literal reading — the host's code as the only root, every provider handed every value: it breaks the
zero-config `OtlpDriver()` the README teaches. Keeping `OtlpSettings(...)` as the override object: a settings class
below the root, the thing the law forbids. The lazy composer and its `LazyProxy`, and `ops/file.FileFinder` that fed it.

