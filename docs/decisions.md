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

**Decision.** `sandbox/compose.yml` — an OpenTelemetry Collector (contrib 0.162.0) writing OTLP/JSON files, and
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
