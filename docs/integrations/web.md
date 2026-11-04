# Web apps

The viewer is a plain ASGI app (`viewer.app`). Serve it on its own port inside your process, or mount it in the web
app you already run — either way it lives in your event loop and reads your live buffer. Install `e-track[viewer]`.

## On its own port

```python
from etrack.providers.adapters.server.granian import GranianAdapter

# granian's Rust server, embedded in your event loop
async with GranianAdapter(viewer.app) as server:
    # http://127.0.0.1:28130
    print(server.url)
```

No second process, no thread of yours, no signal handler taken from you. It refuses a port that is already taken
and raises `ServerError` if the socket does not answer within `ETRACK_SERVER_BOOT`. Host and port:
`ETRACK_SERVER_HOST` (`127.0.0.1`), `ETRACK_SERVER_PORT` (`28130`).

## Mounted in your app

=== "Litestar"

    ```python
    from litestar import Litestar, asgi

    etrack = asgi("/etrack", is_mount=True, copy_scope=True)(viewer.app)
    app = Litestar(route_handlers=[..., etrack])
    ```

=== "FastAPI · Starlette"

    ```python
    app.mount("/etrack", viewer.app)
    ```

The canvas uses relative paths: any prefix works. Link a conversation to its canvas: `/etrack/?thread=<thread_id>`.

## In a lifespan

Open everything on one `AsyncExitStack`, sinks first, the bus last:

```python
from contextlib import AsyncExitStack, asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    async with AsyncExitStack() as stack:
        live = await stack.enter_async_context(LiveAdapter())
        otlp = await stack.enter_async_context(OtlpDriver())
        bus = AnyioAdapter()
        bus.subscribe(live)
        bus.subscribe(otlp)
        await stack.enter_async_context(bus)
        viewer = Viewer(watch=live, topology=LanggraphTopologyAdapter().read(graph))
        # or mount viewer.app
        await stack.enter_async_context(GranianAdapter(viewer.app))
        app.state.tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter())
        yield
```

!!! warning "What it shows is what your agent saw"
    Inputs, outputs and reasoning reach the browser as they are, after your `redact`. Keep it on loopback, or behind
    your app's own authentication when mounted.
