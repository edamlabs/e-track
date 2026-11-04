# Installation

e-track targets **CPython 3.14+**. It is pure Python: one wheel for every platform, the viewer's canvas built in.

=== "uv"

    ```bash
    uv add "e-track[langgraph,otel]"
    ```

=== "pip"

    ```bash
    pip install "e-track[langgraph,otel]"
    ```

## Extras

The core carries the record, the channel, the bus and the live buffer. Everything that speaks to a framework or a
backend is an extra — install what you use:

| Extra | Brings | Install it for |
|---|---|---|
| `langgraph` | `langchain-core`, `langgraph` | tracking LangGraph agents (deepagents included) and reading their graph |
| `otel` | `opentelemetry-sdk`, the OTLP/HTTP exporter, `e-serde` | sending to Langfuse, LangSmith, Phoenix, Tempo or any OpenTelemetry collector |
| `viewer` | `litestar`, `granian`, `e-serde`, `rustworkx` | the live canvas |
| `topology` | `rustworkx` | laying out a graph without the viewer |
| `all` | every extra | |

The core depends on `msgspec`, `structlog`, `anyio` and `pydantic-settings` only.

## Verify

```python
import importlib.metadata

from etrack.logic.api import Tracker

# e.g. 0.1.3
print(importlib.metadata.version("e-track"))
```

The package ships `py.typed`: mypy, pyright and ty check your calls against it.

## From source

```bash
git clone https://github.com/edamlabs/e-track && cd e-track
make install        # uv sync, the canvas's pnpm deps, the prek hooks
make check          # lint · types · architecture · tests
make integration    # real services (docker): a collector and Phoenix, up then down
make ui             # rebuild the viewer's canvas
make docs-serve     # these docs, live at 127.0.0.1:8000
```

Next: [Run it in 3 steps →](quickstart.md)
