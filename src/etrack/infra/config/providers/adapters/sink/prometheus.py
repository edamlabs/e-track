"""infra/config/providers/adapters/sink/prometheus: the metrics' prefix and the latency histogram's buckets."""

from pydantic_settings import SettingsConfigDict

from etrack.infra.config.base import BaseSettings


class PrometheusSettings(BaseSettings):
    """ETRACK_PROMETHEUS_NAMESPACE — every metric's prefix; ETRACK_PROMETHEUS_BUCKETS — span latency buckets, in
    seconds (JSON list)."""

    model_config = SettingsConfigDict(env_prefix="ETRACK_PROMETHEUS_")

    namespace: str = "etrack"
    buckets: tuple[float, ...] = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
