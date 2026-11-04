# Phoenix

Arize Phoenix reads OpenInference, one of the three dialects every span carries. Install `e-track[otel]`.

```bash
docker run -d --rm -p 127.0.0.1:6006:6006 -e PHOENIX_ENABLE_AUTH=false \
  arizephoenix/phoenix:version-21.0.0
```

```bash
ETRACK_OTLP_TARGETS='{"phoenix": {"endpoint": "http://localhost:6006"}}'
ETRACK_OTLP_ATTRIBUTES='{"openinference.project.name": "my-agent"}'
```

| In Phoenix | Comes from |
|---|---|
| project | `openinference.project.name` (else `default`) |
| span kind | `AGENT` (agent, subagent), `LLM`, `TOOL` (tool, mcp), `RETRIEVER`, `EMBEDDING`, `EVALUATOR`, `CHAIN` (the rest) |
| input, output | `input.value`, `output.value` |
| tokens | `llm.token_count.prompt`, `.completion`, `.total` |
| sessions | `session.id` = the thread |

Phoenix 21 authenticates OTLP by default: send its API key in `headers` as Phoenix's authentication docs describe, or
run it with `PHOENIX_ENABLE_AUTH=false` locally. Tested on every change against a live Phoenix 21: the span kinds
come back as Phoenix reads them.
