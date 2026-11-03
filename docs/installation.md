# Installation

Python 3.14 or newer.

```bash
uv add e-track                          # the record, the channel, the bus, the live sink
uv add "e-track[langgraph,otel]"        # + the LangGraph source and the OTLP driver
uv add "e-track[all]"                   # everything
```

| Extra | Brings | For |
|---|---|---|
| `langgraph` | `langchain-core`, `langgraph` | the LangGraph source (deepagents included) and topology |
| `otel` | `opentelemetry-sdk`, the OTLP/HTTP exporter, `e-serde` | the OTLP driver: Langfuse, LangSmith, Phoenix, Tempo, any collector |
| `topology` | `rustworkx` | the layout processor |
| `all` | every extra | |

The core depends on `msgspec`, `structlog`, `anyio` and `pydantic-settings` only. The package ships `py.typed`.

## From source

```bash
git clone https://github.com/edamlabs/e-track && cd e-track
make install        # uv sync + prek hooks
make check          # lint · types · architecture · tests
make integration    # real services: the sandbox comes up and down with the session (needs docker)
```
