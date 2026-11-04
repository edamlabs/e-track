"""tests/unit/etrack/providers/adapters/server: the smallest ASGI app a server can be handed."""

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

type Asgi = Callable[[dict[str, Any], Any, Any], Awaitable[None]]


@pytest.fixture
def hello() -> Asgi:
    """200 and a word for every request, lifespan accepted."""

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        match scope["type"]:
            case "lifespan":
                ### a lifespan loop answers every message until shutdown.
                while (message := await receive())["type"] != "lifespan.shutdown":
                    await send({"type": f"{message['type']}.complete"})
                await send({"type": "lifespan.shutdown.complete"})
            case _:
                await send(
                    {"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]}
                )
                await send({"type": "http.response.body", "body": b"hello"})

    return app
