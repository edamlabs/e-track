"""infra/settings: one `Settings` — every cluster of `infra/config`, read once, at import.

A field is its environment variable, UPPERCASE, exact: `st.ETRACK_OTLP_TARGETS`. A library has no entrypoint of its
own: `infra/defaults` is its composition root and the only module that reads `st`."""

from etrack.infra.config.providers import ProviderSettings


class Settings(ProviderSettings):
    """Every cluster, one contract: read once, at import, from the environment and `.env`."""


settings = Settings()
