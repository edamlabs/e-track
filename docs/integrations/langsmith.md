# LangSmith

Two ways, not exclusive:

- **LangSmith's own LangChain tracer stays.** e-track adds its handler next to whatever callbacks your config already
  carries and pins the run id as LangChain's root run id: the LangSmith trace and the e-track run share one id.
- **Over OpenTelemetry**, through the OTLP driver (`e-track[otel]`):

```bash
ETRACK_OTLP_TARGETS='{"langsmith": {
  "endpoint": "https://api.smith.langchain.com/otel",
  "headers": {"x-api-key": "<key>", "Langsmith-Project": "my-agent"}}}'
```

!!! warning "Not verified yet"
    The GenAI and OpenInference keys LangSmith reads are emitted, but this path has not been checked against
    LangSmith. Confirm the endpoint and headers in LangSmith's OpenTelemetry documentation for your plan and region.
