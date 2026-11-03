"""ports/server: serving an ASGI app from the host's own process — opened, answering at `url`, closed with the host."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from etrack.ports.provider import Provider

### ASGI 3: an app is a coroutine of (scope, receive, send). Frameworks type the three their own way (Litestar's scopes
### are TypedDicts), so the contract stays at the arity every framework's app and every server agree on.
type Asgi = Callable[[Any, Any, Any], Awaitable[None]]


@runtime_checkable
class ServerPort(Provider, Protocol):
    """An app served while the provider is open; `url` is where it answers."""

    @property
    def url(self) -> str: ...
