"""tests/support/hosts: the viewer as a user's web app would carry it — alone, or mounted under a prefix.

Each host takes the viewer's ASGI app and answers the app to serve and the prefix the canvas lives under."""

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from fastapi import FastAPI
from litestar import Litestar, asgi

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from etrack.ports.server import Asgi

PREFIX: Final[str] = "/etrack"


def host_bare(app: Asgi) -> tuple[Asgi, str]:
    """The viewer served on its own: the canvas at the root."""
    return app, ""


def host_fastapi(app: Asgi) -> tuple[Asgi, str]:
    """A FastAPI app with the viewer mounted under `PREFIX`."""
    web = FastAPI()
    web.mount(PREFIX, app)
    return web, PREFIX


def host_litestar(app: Asgi) -> tuple[Asgi, str]:
    """A Litestar app with the viewer mounted under `PREFIX`."""
    return Litestar(route_handlers=[asgi(PREFIX, is_mount=True, copy_scope=True)(app)]), PREFIX


HOSTS: Final[Mapping[str, Callable[[Asgi], tuple[Asgi, str]]]] = MappingProxyType(
    {"bare": host_bare, "fastapi": host_fastapi, "litestar": host_litestar}
)
