"""infra/config/providers/adapters/server/granian: where the viewer listens, and how long it may take to answer."""

from datetime import timedelta

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from etrack.infra.config.base import BaseSettings


class GranianSettings(BaseSettings):
    """ETRACK_SERVER_HOST — the address, loopback by default: the frames carry prompts and tool outputs;
    ETRACK_SERVER_PORT — the port; ETRACK_SERVER_BOOT — how long opening waits for the socket to answer."""

    model_config = SettingsConfigDict(env_prefix="ETRACK_SERVER_")

    host: str = "127.0.0.1"
    port: int = Field(default=28130, ge=1, le=65535)
    boot: timedelta = timedelta(seconds=10)
