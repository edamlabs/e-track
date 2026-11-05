"""infra/config/auth: how a driver authenticates — configuration only; any driver's target carries one.

Picked by `type`, so it reads from the environment as JSON: `{"type": "bearer", "token": "…"}`. Secrets are `SecretStr`,
masked everywhere but at the wire. `google` reads Application Default Credentials (a service account file, the
gcloud login, or the metadata server on Google Cloud) and keeps a fresh OAuth token; `quota_project` is billed for
the calls (`x-goog-user-project`), required by the Telemetry API."""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

CLOUD_PLATFORM: Final[str] = "https://www.googleapis.com/auth/cloud-platform"


class NoAuth(BaseModel):
    """Nothing to present: a local collector, a sidecar, a network that is the boundary."""

    model_config = ConfigDict(frozen=True)

    type: Literal["none"] = "none"


class HeadersAuth(BaseModel):
    """Fixed headers, every value a secret: API keys (`x-api-key`), tenant ids, anything a backend names."""

    model_config = ConfigDict(frozen=True)

    type: Literal["headers"] = "headers"
    headers: dict[str, SecretStr] = Field(default_factory=dict)


class BearerAuth(BaseModel):
    """`Authorization: Bearer <token>`."""

    model_config = ConfigDict(frozen=True)

    type: Literal["bearer"] = "bearer"
    token: SecretStr


class BasicAuth(BaseModel):
    """`Authorization: Basic <user:password>` — Langfuse's keys, Grafana Cloud's instance and token."""

    model_config = ConfigDict(frozen=True)

    type: Literal["basic"] = "basic"
    username: str
    password: SecretStr


class GoogleAuth(BaseModel):
    """Google Application Default Credentials: a token refreshed before it expires, the quota project billed."""

    model_config = ConfigDict(frozen=True)

    type: Literal["google"] = "google"
    scopes: tuple[str, ...] = (CLOUD_PLATFORM,)
    quota_project: str = ""


type Auth = Annotated[NoAuth | HeadersAuth | BearerAuth | BasicAuth | GoogleAuth, Field(discriminator="type")]
