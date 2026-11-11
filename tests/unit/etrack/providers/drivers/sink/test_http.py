"""tests/unit/etrack/providers/drivers/sink/http: batches leave full or on time, signed, retried when worth it, never twice."""

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs
from werkzeug.wrappers import Request, Response

from etrack.infra.config.auth import BearerAuth
from etrack.infra.config.providers import Encoding
from etrack.infra.errors import SinkError
from etrack.models.event import EventKind, EventPhase, Outcome, RunView
from etrack.ports.sink import Refusal, SinkPort
from etrack.providers.drivers.sink.http import HttpDriver
from support.endpoint import PATH, fake_endpoint
from support.port import free_port
from support.recall import Recall, RecallDriver
from support.wait import eventually
from unit.etrack.conftest import RUN, frame

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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


class Keeping(HttpDriver):
    """Keeps what was refused, as a host would."""

    def __init__(self, **given: Any) -> None:
        super().__init__(**given)
        self.refusals: list[tuple[int, Refusal]] = []

    def refused(self, items: Sequence[Any], refusal: Refusal) -> None:
        self.refusals.append((len(items), refusal))


@pytest.mark.parametrize(
    ("statuses", "attempts", "final"), [((503,) * 4, 4, False), ((422,), 1, True)], ids=["exhausted", "final"]
)
async def test_http_gives_up(
    settings: Configure, httpserver: HTTPServer, statuses: tuple[int, ...], attempts: int, final: bool
) -> None:
    endpoint = fake_endpoint(httpserver, *statuses)
    async with Keeping(**settings(endpoint.url)) as driver:
        await driver.send(frame())
        assert (await driver.flush(), driver.failed) == (0, 1)
        assert await driver.flush() == 0
    ((count, refusal),) = driver.refusals
    assert (count, refusal.status, refusal.final) == (1, statuses[0], final)
    assert f"after {attempts} attempts" in refusal.reason
    assert len(endpoint.bodies) == attempts


async def test_http_unreachable(settings: Configure) -> None:
    async with Keeping(**settings(f"http://127.0.0.1:{free_port()}/events", retries=1)) as driver:
        await driver.send(frame())
        assert await driver.flush() == 0
    ((_, refusal),) = driver.refusals
    assert (refusal.status, refusal.final) == (0, False)
    assert "ConnectError" in refusal.reason


async def test_http_timer_logs_a_refusal(settings: Configure, httpserver: HTTPServer) -> None:
    endpoint = fake_endpoint(httpserver, 400)
    config = settings(endpoint.url, flush=timedelta(milliseconds=20))
    with capture_logs() as lines:
        async with HttpDriver(**config) as driver:
            await driver.send(frame())
            await eventually(lambda: any(line["event"] == "http refused" for line in lines))
    (line,) = [line for line in lines if line["event"] == "http refused"]
    assert (line["status"], line["final"], line["items"]) == (400, True, 1)


async def test_http_bad_item_costs_one(settings: Configure, httpserver: HTTPServer) -> None:
    taken: list[int] = []

    def handler(request: Request) -> Response:
        seqs = [json.loads(line)["seq"] for line in request.get_data().splitlines()]
        match 1 in seqs:
            case True:
                return Response("seq 1: field required", status=422)
            case _:
                taken.extend(seqs)
                return Response(status=202)

    httpserver.expect_request(PATH).respond_with_handler(handler)
    async with Keeping(**settings(httpserver.url_for(PATH), batch=3)) as driver:
        _ = [await driver.send(frame(seq)) for seq in range(3)]
    assert (sorted(taken), driver.sent, driver.failed) == ([0, 2], 2, 1)
    ((count, refusal),) = driver.refusals
    assert (count, refusal.status, refusal.final) == (1, 422, True)
    assert "seq 1: field required" in refusal.reason


async def test_http_own_signer(settings: Configure, httpserver: HTTPServer) -> None:
    class Identity:
        async def headers(self) -> Mapping[str, str]:
            return {"Authorization": "Bearer id-token"}

    endpoint = fake_endpoint(httpserver)
    async with HttpDriver(signer=Identity(), **settings(endpoint.url)) as driver:
        await driver.send(frame())
    assert endpoint.headers[0]["Authorization"] == "Bearer id-token"


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
