# Langfuse

Langfuse ingests OpenTelemetry: point the OTLP driver at it. Install `e-track[otel]`.

```bash
ETRACK_OTLP_TARGETS='{"langfuse": {
  "endpoint": "https://cloud.langfuse.com/api/public/otel",
  "headers": {"Authorization": "Basic <base64 of public_key:secret_key>"}}}'
```

Self-hosted: `http://<host>:3000/api/public/otel`. Build the header with
`printf '%s' "pk-lf-…:sk-lf-…" | base64 -w0`.

| In Langfuse | Comes from |
|---|---|
| sessions | the thread (`langfuse.session.id`) |
| trace | the run — its id is the run id |
| observation types | the span kind: `generation` (llm), `tool` (tool, mcp), `agent` (agent, subagent), `retriever`, `embedding`, `evaluator`, `chain` (run, node), `span` (the rest) |
| usage and cost | exclusive buckets: `input`, `output`, `input_cache_read`, `input_cache_creation`, `output_reasoning` — cached input is priced as cached |
| metadata | the root span's `app.*` attributes (→ [LangGraph](langgraph.md#the-runs-own-facts)) |

Measured against Langfuse's own LangChain handler on the same runs (deeptrack's tracing A/B): the same nesting,
generations and tokens. Before 0.1.2 cached input was priced at the full input rate — up to twice the cost; it is
priced apart since. Everything else about the driver → [OpenTelemetry](opentelemetry.md).
