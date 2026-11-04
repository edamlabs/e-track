"""infra/config/providers/drivers/sink/http: where an HTTP sink sends, how it signs, how it batches and how it retries.

`ETRACK_HTTP_*` configures the one driver read from settings; a custom driver built on `HttpDriver` takes its own
`HttpSettings(...)` — one endpoint per instance, as many instances as systems."""

from datetime import timedelta
from enum import StrEnum, auto
from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from etrack.infra.config.auth import Auth, NoAuth
from etrack.infra.config.base import BaseSettings, Secret


class Encoding(StrEnum):
    """How a batch travels: one JSON array, or one JSON object per line (`application/x-ndjson`)."""

    JSON = auto()
    NDJSON = auto()


class HttpSettings(BaseSettings):
    """ETRACK_HTTP_ENDPOINT — the URL every batch is sent to (empty: nothing leaves); ETRACK_HTTP_METHOD — POST or PUT;
    ETRACK_HTTP_AUTH — how it signs (JSON: `{"type": "bearer", "token": …}`); ETRACK_HTTP_HEADERS — fixed headers;
    ETRACK_HTTP_ENCODING — json or ndjson; ETRACK_HTTP_BATCH — events per request at most; ETRACK_HTTP_FLUSH — the
    longest an event waits for its batch; ETRACK_HTTP_TIMEOUT — per request; ETRACK_HTTP_RETRIES — attempts after the
    first on a network error, 429 or 5xx; ETRACK_HTTP_BACKOFF — the first wait, doubled each retry; ETRACK_HTTP_KINDS —
    the kinds sent (empty: every kind)."""

    model_config = SettingsConfigDict(env_prefix="ETRACK_HTTP_")

    endpoint: str = ""
    method: Literal["POST", "PUT"] = "POST"
    auth: Auth = Field(default_factory=NoAuth)
    headers: dict[str, Secret] = Field(default_factory=dict)
    encoding: Encoding = Encoding.NDJSON
    batch: int = Field(default=100, ge=1)
    flush: timedelta = timedelta(seconds=1)
    timeout: timedelta = timedelta(seconds=10)
    retries: int = Field(default=3, ge=0)
    backoff: timedelta = timedelta(milliseconds=500)
    ### kind names (`llm`, `retrieval`…): config never imports the record, the driver compares them to its kinds.
    kinds: frozenset[str] = frozenset()
