"""infra/auth: AuthSigner — one configured `Auth` turned into what goes on the wire, for any driver.

Static kinds sign at once: fixed headers, a bearer token, basic credentials. `google` resolves Application Default
Credentials once, off the loop (`ready`), and refreshes the token off the loop whenever it is no longer valid; its
headers carry `Authorization` and the quota project. A driver built on `requests` (the OTLP exporters) takes
`session()` instead — google-auth's `AuthorizedSession` refreshes on its own and retries a 401 once refreshed."""

import base64
from typing import TYPE_CHECKING, Self

import anyio
import google.auth
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.auth.transport.requests import AuthorizedSession, Request

from etrack.infra.config.auth import BasicAuth, BearerAuth, GoogleAuth, HeadersAuth
from etrack.infra.errors import AuthError

if TYPE_CHECKING:
    import requests
    from google.auth.credentials import Credentials

    from etrack.infra.config.auth import Auth


class AuthSigner:
    """Signs a driver's requests with one `Auth`; Google credentials may be handed in (tests, a custom chain)."""

    __slots__ = ("_auth", "_credentials")

    def __init__(self, auth: Auth, credentials: Credentials | None = None) -> None:
        self._auth = auth
        self._credentials = credentials

    ##### PRIVATE #####

    @staticmethod
    def _ready_default(auth: GoogleAuth) -> Credentials:
        """Application Default Credentials for the scopes, billed to the quota project when one is set."""
        try:
            found, _ = google.auth.default(scopes=list(auth.scopes), quota_project_id=auth.quota_project or None)
        except DefaultCredentialsError as failure:
            msg = f"google: no Application Default Credentials — {failure}"
            raise AuthError(msg) from failure
        return found

    def _common_credentials(self) -> Credentials:
        match self._credentials:
            case None:
                msg = "AuthSigner: google credentials are not resolved — await ready() before signing"
                raise AuthError(msg)
            case found:
                return found

    @staticmethod
    def _headers_refresh(credentials: Credentials) -> None:
        try:
            credentials.refresh(Request())
        except RefreshError as failure:
            msg = f"google: the token cannot be refreshed — {failure}"
            raise AuthError(msg) from failure

    ############################################################

    ##### PUBLIC #####

    async def ready(self) -> Self:
        """Resolve what signing needs before the first request: Google credentials, off the loop; nothing otherwise."""
        match self._auth, self._credentials:
            case GoogleAuth() as auth, None:
                self._credentials = await anyio.to_thread.run_sync(self._ready_default, auth)
            case _:
                pass
        return self

    def static(self) -> dict[str, str]:
        """The headers that never change: everything but a refreshing token."""
        match self._auth:
            case HeadersAuth(headers=headers):
                return {key: secret.get_secret_value() for key, secret in headers.items()}
            case BearerAuth(token=token):
                return {"Authorization": f"Bearer {token.get_secret_value()}"}
            case BasicAuth(username=username, password=password):
                pair = f"{username}:{password.get_secret_value()}".encode()
                return {"Authorization": f"Basic {base64.b64encode(pair).decode()}"}
            case _:
                ### none, and google: its token is never static.
                return {}

    async def headers(self) -> dict[str, str]:
        """Every header for the next request, a Google token refreshed off the loop when it is no longer valid."""
        signed = self.static()
        match self._auth:
            case GoogleAuth():
                credentials = self._common_credentials()
                _ = credentials.valid or await anyio.to_thread.run_sync(self._headers_refresh, credentials)
                credentials.apply(signed)
            case _:
                pass
        return signed

    def session(self) -> requests.Session | None:
        """For a driver built on `requests`: Google's refreshing session, or none — the static headers suffice."""
        match self._auth:
            case GoogleAuth():
                return AuthorizedSession(self._common_credentials())
            case _:
                return None
