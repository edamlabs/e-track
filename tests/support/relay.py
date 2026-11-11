"""tests/support/relay: a host that stores runs for an endpoint that is down, then waits to be killed.

Run as a script: `relay.py <db> <url> <count>` publishes `count` run ENDs through a guaranteed subscription, prints
`stored` once all of them are in the outbox, and sleeps — the test kills it with SIGKILL."""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Unpack

from etrack.models.event import EventKind, EventPhase, EventView, RunEvent
from etrack.ports.bus import Delivery
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.outbox.sqlite import SqliteAdapter
from etrack.providers.drivers.sink.http import HttpDriver

if TYPE_CHECKING:
    from etrack.infra.config.providers import HttpConfig

FAST: HttpConfig = {
    "batch": 10,
    "retries": 0,
    "schedule": (timedelta(milliseconds=50),),
    "lease": timedelta(milliseconds=200),
    "poll": timedelta(milliseconds=50),
    "backoff": timedelta(milliseconds=1),
}


def fast(url: str, **more: Unpack[HttpConfig]) -> HttpConfig:
    """A relay that tries at once and often, toward `url`, with `more` on top."""
    return {**FAST, **more, "endpoint": url}


class TurnDriver(HttpDriver):
    """Run ENDs only, keyed by their run: the key the receiver deduplicates by."""

    phases = frozenset({EventPhase.END})

    def accept(self, view: EventView) -> bool:
        return isinstance(view, RunEvent) and view.kind is EventKind.RUN

    def encode(self, view: EventView) -> Any:
        return {"turn": RunEvent.project(view).run_id}

    def key(self, view: EventView, content: bytes) -> str:
        return RunEvent.project(view).run_id


def ended(index: int) -> RunEvent:
    run = f"{index:032x}"
    return RunEvent(run_id=run, seq=0, id=run, kind=EventKind.RUN, phase=EventPhase.END)


async def host(db: Path, url: str, count: int) -> None:
    async with SqliteAdapter(db) as outbox, TurnDriver(outbox=outbox, **fast(url)) as driver:
        bus = AnyioAdapter(capacity=1)
        bus.subscribe(driver, delivery=Delivery.GUARANTEED)
        async with bus:
            _ = [bus.publish(ended(index)) for index in range(count)]
            while (await driver.report()).pending < count:  # noqa: ASYNC110 — the count is read from a file, not awaited
                await asyncio.sleep(0.01)
            print("stored", flush=True)  # noqa: T201 — the parent reads this line
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(host(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])))
