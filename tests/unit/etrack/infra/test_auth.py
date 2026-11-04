"""tests/unit/etrack/infra/auth: every configured Auth signs what it should; Google refreshes off the loop, only when due."""

from typing import Any

import google.auth
import pytest
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import AuthorizedSession

from etrack.infra.auth import AuthSigner
from etrack.infra.config.auth import BasicAuth, BearerAuth, GoogleAuth, HeadersAuth, NoAuth
from etrack.infra.config.base import Secret
from etrack.infra.errors import AuthError
from support.credentials import FakeCredentials


@pytest.mark.parametrize(
    ("auth", "expected"),
    [
        (NoAuth(), {}),
        (HeadersAuth(headers={"x-api-key": Secret("k")}), {"x-api-key": "k"}),
        (BearerAuth(token=Secret("t")), {"Authorization": "Bearer t"}),
        (BasicAuth(username="u", password=Secret("p")), {"Authorization": "Basic dTpw"}),
    ],
    ids=["none", "headers", "bearer", "basic"],
)
async def test_auth_static_kinds(auth: Any, expected: dict[str, str]) -> None:
    signer = await AuthSigner(auth).ready()
    assert (signer.static(), await signer.headers(), signer.session()) == (expected, expected, None)


async def test_auth_google_refreshes_only_when_due() -> None:
    credentials = FakeCredentials("billing")
    signer = await AuthSigner(GoogleAuth(), credentials).ready()
    first, second = await signer.headers(), await signer.headers()
    assert first == second == {"authorization": "Bearer token-1", "x-goog-user-project": "billing"}
    assert credentials.refreshes == 1
    assert signer.static() == {}
    assert isinstance(signer.session(), AuthorizedSession)


async def test_auth_google_reads_default_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: dict[str, Any] = {}

    def default(**kwargs: Any) -> tuple[FakeCredentials, str]:
        asked.update(kwargs)
        return FakeCredentials(kwargs["quota_project_id"]), "project"

    monkeypatch.setattr(google.auth, "default", default)
    signer = await AuthSigner(GoogleAuth(quota_project="billing")).ready()
    assert (await signer.headers())["x-goog-user-project"] == "billing"
    assert asked["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]


async def test_auth_google_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def default(**kwargs: Any) -> None:
        msg = "no ADC"
        raise DefaultCredentialsError(msg)

    monkeypatch.setattr(google.auth, "default", default)
    with pytest.raises(AuthError, match="no Application Default Credentials"):
        await AuthSigner(GoogleAuth()).ready()


async def test_auth_google_unresolved() -> None:
    with pytest.raises(AuthError, match="await ready"):
        await AuthSigner(GoogleAuth()).headers()


async def test_auth_google_refresh_refused() -> None:
    signer = await AuthSigner(GoogleAuth(), FakeCredentials(broken=True)).ready()
    with pytest.raises(AuthError, match="cannot be refreshed"):
        await signer.headers()
