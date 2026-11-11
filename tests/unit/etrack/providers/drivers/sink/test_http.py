"""tests/unit/etrack/providers/drivers/sink/http: batches leave full or on time, signed, retried when worth it, never twice."""

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from etrack.infra.config.auth import BearerAuth
from etrack.infra.config.providers import Encoding
from etrack.infra.errors import SinkError
from etrack.models.event import EventKind, EventPhase, Outcome, RunView
from etrack.ports.sink import SinkPort
from etrack.providers.drivers.sink.http import HttpDriver
from support.endpoint import fake_endpoint
from support.port import free_port
from support.recall import Recall, RecallDriver
from support.wait import eventually
from unit.etrack.conftest import RUN, frame

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer

    from unit.etrack.providers.drivers.sink.conftest import Configure


async def test_http_meets_port() -> None:
    assert isinstance(HttpDriver(), SinkPort)
    assert HttpDriver().accept(frame())


async def test_http_full_batch_leaves_rest_on_close(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver)
    async with HttpDriver(**settings(endpoint.url, batch=2)) as driver:
        _ = [await driver.send(frame(seq)) for seq in range(3)]
        assert len(endpoint.bodies) == 1
    lines = [[json.loads(line)["seq"] for line in body.splitlines()] for body in endpoint.bodies]
    assert lines == [[0, 1], [2]]
    assert endpoint.headers[0]["Content-Type"] == "application/x-ndjson"
    assert driver.sent == 3


async def test_http_batch_leaves_on_time(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver)
    config = settings(endpoint.url, flush=timedelta(milliseconds=20))
    async with HttpDriver(**config) as driver:
        await driver.send(frame())
        await eventually(lambda: len(endpoint.bodies) == 1)
        assert await driver.health()
    assert not await driver.health()


async def test_http_json_signed_filtered(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver)
    config = settings(
        endpoint.url,
        encoding=Encoding.JSON,
        auth=BearerAuth(token=SecretStr("t")),
        headers={"x-tenant": SecretStr("acme")},
        kinds=frozenset({EventKind.LLM}),
    )
    async with HttpDriver(**config) as driver:
        await driver.send(frame(0, kind=EventKind.NODE))
        await driver.send(frame(1, kind=EventKind.LLM))
    (body,) = endpoint.bodies
    assert [item["seq"] for item in json.loads(body)] == [1]
    assert (endpoint.headers[0]["Authorization"], endpoint.headers[0]["X-Tenant"]) == ("Bearer t", "acme")


async def test_http_retries_until_accepted(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver, 503, 429)
    async with HttpDriver(**settings(endpoint.url)) as driver:
        await driver.send(frame())
        assert await driver.flush() == 1
    assert len(endpoint.bodies) == 3


@pytest.mark.parametrize(("statuses", "attempts"), [((503,) * 4, 4), ((400,), 1)], ids=["exhausted", "refused"])
async def test_http_gives_up(
    settings: Configure, httpserver: HTTPServer, statuses: tuple[int, ...], attempts: int
) -> None:
    endpoint = fake_endpoint(httpserver, *statuses)
    async with HttpDriver(**settings(endpoint.url)) as driver:
        await driver.send(frame())
        with pytest.raises(SinkError, match=f"after {attempts} attempts"):
            await driver.flush()
        assert (driver.failed, await driver.flush()) == (1, 0)
    assert len(endpoint.bodies) == attempts


async def test_http_unreachable(settings: Configure) -> None:
    async with HttpDriver(**settings(f"http://127.0.0.1:{free_port()}/events", retries=1)) as driver:
        await driver.send(frame())
        with pytest.raises(SinkError, match="ConnectError"):
            await driver.flush()


async def test_http_timer_logs_a_refusal(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver, 400)
    config = settings(endpoint.url, flush=timedelta(milliseconds=20))
    with capture_logs() as lines:
        async with HttpDriver(**config) as driver:
            await driver.send(frame())
            await eventually(lambda: any(line["event"] == "http flush failed" for line in lines))


async def test_http_closed(settings: Configure) -> None:
    driver = HttpDriver(**settings("http://127.0.0.1:1/events"))
    with pytest.raises(SinkError, match="not open"):
        await driver.send(frame())
    await driver.__aexit__(None, None, None)


async def test_http_subclass_hooks(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver)
    async with RecallDriver(**settings(endpoint.url)) as driver:
        await driver.send(Recall.project(frame(0, EventPhase.END, kind=EventKind.TOOL)))
        await driver.send(
            Recall.project(frame(1, EventPhase.END, kind=EventKind.RETRIEVAL, name="poliza", payload={"hits": ["a"]}))
        )
    assert json.loads(endpoint.bodies[0]) == {"recalls": [{"run": frame().run_id, "query": "poliza", "hits": ["a"]}]}


##### GATE #####
class ConsentedDriver(HttpDriver):
    """Runs whose customer consented and is known, and that completed."""

    view = RunView
    phases = frozenset({EventPhase.END, EventPhase.ERROR})

    def accept(self, view: Any) -> bool:
        run = RunView.project(view)
        consented = run.ended and run.attributes["app.consent"] and run.attributes["app.known"]
        return bool(consented) and run.outcome is Outcome.COMPLETED

    def encode(self, view: Any) -> Any:
        run = RunView.project(view)
        return {"turn": run.run_id, "user": run.input, "assistant": run.output}


def _ended(**attributes: Any) -> Any:
    return frame(
        9,
        EventPhase.END,
        id=RUN,
        kind=EventKind.RUN,
        input="hola",
        output="buenas",
        outcome=Outcome.COMPLETED,
        attributes=attributes,
    )


@pytest.mark.parametrize(
    ("attributes", "sent", "missing"),
    [
        ({"app.consent": True, "app.known": True}, 1, 0),
        ({"app.consent": False, "app.known": True}, 0, 0),
        ({"app.consent": True, "app.known": False}, 0, 0),
        ({"app.consent": True}, 0, 1),
        ({}, 0, 1),
    ],
    ids=["both", "no-consent", "unknown", "known-absent", "none"],
)
async def test_http_gate_fails_closed(
    attributes: dict[str, Any], sent: int, missing: int, *, settings: Configure, httpserver: HTTPServer
) -> None:
    endpoint = fake_endpoint(httpserver)
    async with ConsentedDriver(**settings(endpoint.url)) as driver:
        await driver.send(_ended(**attributes))
    assert (driver.sent, driver.missing) == (sent, missing)
    assert [json.loads(body) for body in endpoint.bodies] == [
        {"turn": RUN, "user": "hola", "assistant": "buenas"}
    ] * sent


@pytest.mark.parametrize(
    ("fields", "ended"),
    [
        ({"kind": EventKind.RUN, "phase": EventPhase.END}, True),
        ({"kind": EventKind.RUN, "phase": EventPhase.ERROR}, True),
        ({"kind": EventKind.RUN, "phase": EventPhase.START}, False),
        ({"kind": EventKind.RUN, "phase": EventPhase.END, "parent": "up"}, False),
        ({"kind": EventKind.NODE, "phase": EventPhase.END}, False),
    ],
    ids=["end", "error", "start", "nested", "node"],
)
async def test_http_run_view_ended(fields: dict[str, Any], ended: bool) -> None:
    assert RunView.project(frame(**fields)).ended is ended
