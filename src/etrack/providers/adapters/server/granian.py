"""providers/adapters/server/granian: GranianAdapter — an ASGI app served by granian's embedded server, in-process.

granian's Rust runtime serves the app as a task of the host's own event loop: no second process, no thread of ours,
no signal handler taken from the host. Opening starts the server and waits until its socket answers; closing stops it
and waits for it to drain. The app is anything ASGI — the viewer's, or a host's own."""

import asyncio
import socket
from typing import TYPE_CHECKING, ClassVar, Final, Self, Unpack

from granian.constants import Interfaces
from granian.server.embed import Server

from etrack.infra import defaults
from etrack.infra.errors import ServerError
from etrack.infra.logger import logger
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from etrack.infra.config.providers import GranianConfig
    from etrack.ports.server import Asgi

PAUSE: Final[float] = 0.02


class GranianAdapter:
    """One app on one address, served for as long as the adapter is open."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("granian", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    __slots__ = ("_app", "_conf", "_server", "_task")

    def __init__(self, app: Asgi, **given: Unpack[GranianConfig]) -> None:
        self._app = app
        self._conf = defaults.granian(**given)
        self._server: Server | None = None
        self._task: asyncio.Task[None] | None = None

    ##### PRIVATE #####

    @staticmethod
    def _enter_free(host: str, port: int) -> None:
        ### a port someone else listens on would answer the probe for a server that never bound: refuse it up front.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError as taken:
                msg = f"granian: {host}:{port} is taken"
                raise ServerError(msg) from taken

    async def _enter_answering(self, task: asyncio.Task[None]) -> None:
        config = self._conf
        ### granian's startup hooks fire before the socket listens: a connection accepted is the only proof.
        try:
            async with asyncio.timeout(config["boot"].total_seconds()):
                while not await self._enter_probe(task, config["host"], config["port"]):  # noqa: ASYNC110 — a socket signals nothing
                    await asyncio.sleep(PAUSE)
        except TimeoutError as late:
            msg = f"granian: {self.url} did not answer within {config['boot']}"
            raise ServerError(msg) from late

    @staticmethod
    async def _enter_probe(task: asyncio.Task[None], host: str, port: int) -> bool:
        match task.done():
            case True:
                msg = f"granian: the server on {host}:{port} stopped before it answered"
                raise ServerError(msg) from task.exception()
            case _:
                try:
                    _, writer = await asyncio.open_connection(host, port)
                except OSError:
                    return False
                writer.close()
                await writer.wait_closed()
                return True

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        config = self._conf
        self._enter_free(config["host"], config["port"])
        self._server = Server(
            self._app, address=config["host"], port=config["port"], interface=Interfaces.ASGI, log_enabled=False
        )
        self._task = asyncio.create_task(self._server.serve())
        try:
            await self._enter_answering(self._task)
        except ServerError:
            await self.__aexit__(None, None, None)
            raise
        logger.info("server opened", url=self.url)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._server, self._task:
            case Server() as server, asyncio.Task() as task:
                _ = task.done() or server.stop()
                ### a server that died on its own already said why on opening: exit only waits for it to end.
                await asyncio.wait({task})
                self._server = self._task = None
                logger.info("server closed", url=self.url)
            case _:
                return

    async def health(self) -> bool:
        """Serving: the server's task still runs."""
        return self._task is not None and not self._task.done()

    @property
    def url(self) -> str:
        """Where the app answers: `http://host:port`."""
        config = self._conf
        return f"http://{config['host']}:{config['port']}"
