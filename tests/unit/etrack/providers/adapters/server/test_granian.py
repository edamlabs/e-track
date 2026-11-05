"""tests/unit/etrack/providers/adapters/server/granian: serve in the host's loop, refuse a taken port, never hang."""

import socket
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx
import pytest

from etrack.infra.config.providers import GranianConfig
from etrack.infra.errors import ServerError
from etrack.ports.server import ServerPort
from etrack.providers.adapters.server import granian as module
from etrack.providers.adapters.server.granian import GranianAdapter
from support.port import free_port

if TYPE_CHECKING:
    from unit.etrack.providers.adapters.server.conftest import Asgi


async def test_granian_meets_port_and_serves(hello: Asgi) -> None:
    settings = GranianConfig(port=free_port())
    async with GranianAdapter(hello, **settings) as server, httpx.AsyncClient() as client:
        assert isinstance(server, ServerPort)
        assert await server.health()
        assert server.url == f"http://127.0.0.1:{settings['port']}"
        assert (await client.get(server.url)).text == "hello"
    assert not await server.health()


async def test_granian_refuses_taken_port(hello: Asgi) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        settings = GranianConfig(port=taken.getsockname()[1])
        with pytest.raises(ServerError, match="is taken"):
            await GranianAdapter(hello, **settings).__aenter__()


async def test_granian_boot_timeout(monkeypatch: pytest.MonkeyPatch, hello: Asgi) -> None:
    async def never(*_: object) -> bool:
        return False

    monkeypatch.setattr(GranianAdapter, "_enter_probe", staticmethod(never))
    adapter = GranianAdapter(hello, **GranianConfig(port=free_port(), boot=timedelta(milliseconds=100)))
    with pytest.raises(ServerError, match="did not answer"):
        await adapter.__aenter__()
    assert not await adapter.health()


async def test_granian_server_dies_before_answering(monkeypatch: pytest.MonkeyPatch, hello: Asgi) -> None:
    class Dead:
        def __init__(self, *_: object, **__: object) -> None: ...

        async def serve(self) -> None:
            msg = "cannot bind"
            raise OSError(msg)

        def stop(self) -> None: ...

    monkeypatch.setattr(module, "Server", Dead)
    adapter = GranianAdapter(hello, **GranianConfig(port=free_port()))
    with pytest.raises(ServerError, match="stopped before it answered"):
        await adapter.__aenter__()
    assert not await adapter.health()


async def test_granian_exit_unopened(hello: Asgi) -> None:
    adapter = GranianAdapter(hello, **GranianConfig(port=free_port()))
    await adapter.__aexit__(None, None, None)
    assert not await adapter.health()
