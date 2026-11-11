"""tests/unit/etrack/providers/drivers/sink/http (outbox): stored before sent, relayed, given up, requeued, never lost."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from werkzeug.wrappers import Request, Response

from etrack.ports.bus import Delivery
from etrack.ports.outbox import EntryState
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.outbox.sqlite import SqliteAdapter
from etrack.providers.drivers.sink.http import HttpDriver
from support.endpoint import PATH, fake_endpoint
from support.port import free_port
from support.relay import TurnDriver, ended, fast
from support.wait import eventually

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pytest_httpserver import HTTPServer

    from etrack.ports.sink import Refusal

RELAY = Path(__file__).resolve().parents[5] / "support" / "relay.py"


class Keeping(TurnDriver):
    def __init__(self, **given: Any) -> None:
        super().__init__(**given)
        self.refusals: list[Refusal] = []

    def refused(self, items: Sequence[Any], refusal: Refusal) -> None:
        self.refusals.append(refusal)


async def test_outbox_delivered_and_acked(tmp_path: Path, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver)
    async with (
        SqliteAdapter(tmp_path / "o.db") as outbox,
        TurnDriver(outbox=outbox, **fast(endpoint.url)) as driver,
    ):
        _ = [await driver.send(ended(index)) for index in range(3)]
        await eventually(lambda: driver.sent == 3)
        assert (await outbox.report())[EntryState.PENDING] == 0
    turns = [json.loads(line)["turn"] for body in endpoint.bodies for line in body.splitlines()]
    assert sorted(turns) == [f"{index:032x}" for index in range(3)]


async def test_outbox_one_bad_item_dead_rest_delivered(tmp_path: Path, httpserver: HTTPServer) -> None:
    bad = f"{1:032x}"
    taken: list[str] = []

    def handler(request: Request) -> Response:
        turns = [json.loads(line)["turn"] for line in request.get_data().splitlines()]
        match bad in turns:
            case True:
                return Response("turn_id: field required", status=422)
            case _:
                taken.extend(turns)
                return Response(status=202)

    httpserver.expect_request(PATH).respond_with_handler(handler)
    async with (
        SqliteAdapter(tmp_path / "o.db") as outbox,
        Keeping(outbox=outbox, **fast(httpserver.url_for(PATH))) as driver,
    ):
        _ = [await driver.send(ended(index)) for index in range(3)]
        await eventually(lambda: driver.sent == 2 and driver.failed == 1)
        dead = await outbox.of(bad)
        report = await driver.report()
    assert dead is not None
    assert sorted(taken) == [f"{0:032x}", f"{2:032x}"]
    assert (dead.state, "field required" in dead.reason) == (EntryState.DEAD, True)
    assert (driver.refusals[0].status, driver.refusals[0].final) == (422, True)
    assert (report.sent, report.failed, report.pending, report.dead) == (2, 1, 0, 1)


async def test_outbox_deadline_then_requeue(tmp_path: Path, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver, 503, 503, 503)
    config = fast(endpoint.url, deadline=timedelta(milliseconds=100))
    async with SqliteAdapter(tmp_path / "o.db") as outbox, Keeping(outbox=outbox, **config) as driver:
        await driver.send(ended(0))
        key = f"{0:032x}"
        await eventually(lambda: driver.failed == 1)
        dead = await outbox.of(key)
        assert dead is not None
        assert dead.state is EntryState.DEAD
        assert "past its deadline" in driver.refusals[0].reason
        assert await outbox.requeue(key)
        await eventually(lambda: driver.sent == 1)
        assert await outbox.of(key) is None


async def test_outbox_retry_waits_its_schedule(tmp_path: Path, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver, 503)
    async with (
        SqliteAdapter(tmp_path / "o.db") as outbox,
        TurnDriver(outbox=outbox, **fast(endpoint.url)) as driver,
    ):
        await driver.send(ended(0))
        await eventually(lambda: driver.sent == 1)
    assert len(endpoint.bodies) == 2


async def test_outbox_full_bus_never_drops(tmp_path: Path, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver)
    async with (
        SqliteAdapter(tmp_path / "o.db") as outbox,
        TurnDriver(outbox=outbox, **fast(endpoint.url)) as driver,
    ):
        bus = AnyioAdapter(capacity=1)
        bus.subscribe(driver, delivery=Delivery.GUARANTEED)
        async with bus:
            _ = [bus.publish(ended(index)) for index in range(200)]
        await eventually(lambda: driver.sent == 200)
        assert bus.dropped == {}


async def test_outbox_killed_host_loses_nothing(tmp_path: Path, httpserver: HTTPServer) -> None:
    db, count = tmp_path / "o.db", 100
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    down = f"http://127.0.0.1:{free_port()}{PATH}"
    host = await asyncio.create_subprocess_exec(
        sys.executable, str(RELAY), str(db), down, str(count), stdout=subprocess.PIPE, env=env
    )
    assert host.stdout is not None
    ### the host's log shares its stdout: read until it says everything is stored.
    async with asyncio.timeout(30):
        while (await host.stdout.readline()).strip() != b"stored":
            pass
    ### SIGKILL on POSIX, TerminateProcess on Windows: the host gets no chance to close anything.
    host.kill()
    await host.wait()
    endpoint = fake_endpoint(httpserver)
    async with SqliteAdapter(db) as outbox, TurnDriver(outbox=outbox, **fast(endpoint.url)) as driver:
        await eventually(lambda: driver.sent == count)
        assert (await driver.report()).pending == 0
    turns = [json.loads(line)["turn"] for body in endpoint.bodies for line in body.splitlines()]
    assert sorted(turns) == [f"{index:032x}" for index in range(count)]


async def test_outbox_default_key_is_content(tmp_path: Path, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver, 503)
    config = fast(endpoint.url, schedule=(timedelta(hours=1),))
    async with SqliteAdapter(tmp_path / "o.db") as outbox, HttpDriver(outbox=outbox, **config) as driver:
        same = ended(0)
        _ = [await driver.send(same) for _ in range(2)]
        await eventually(lambda: len(endpoint.bodies) == 1)
        assert (await driver.report()).pending == 1
