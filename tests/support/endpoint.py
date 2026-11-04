"""tests/support/endpoint: an HTTP endpoint a sink posts to — real sockets, scripted answers, every request kept."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from werkzeug.wrappers import Request, Response

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer

PATH = "/events"


@dataclass
class FakeEndpoint:
    """The URL to post to, the statuses it answers in order (200 once they run out), and what it received."""

    url: str
    statuses: list[int]
    bodies: list[bytes] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)


def fake_endpoint(server: HTTPServer, *statuses: int) -> FakeEndpoint:
    """Mount `PATH` on the server, answering `statuses` first and 200 after."""
    endpoint = FakeEndpoint(url=server.url_for(PATH), statuses=list(statuses))

    def handler(request: Request) -> Response:
        endpoint.headers.append(dict(request.headers))
        endpoint.bodies.append(request.get_data())
        status = endpoint.statuses.pop(0) if endpoint.statuses else 200
        return Response(status=status)

    server.expect_request(PATH).respond_with_handler(handler)
    return endpoint
