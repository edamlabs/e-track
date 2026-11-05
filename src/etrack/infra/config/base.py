"""infra/config/base: pydantic-settings — frozen, typed, layered config, one shape for every cluster.

Every cluster inherits from here, and `infra/settings` merges them into the one `Settings`. The layers, lowest first:
config file < secrets < `.env` < environment < kwargs. A field is its environment variable, UPPERCASE, exact: there
is no prefix to add and no alias to remember. Credentials are `SecretStr`, masked everywhere but at the wire."""

from typing import Final

from pydantic_settings import (
    BaseSettings as SettingsBase,
)
from pydantic_settings import (
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
    YamlConfigSettingsSource,
)

FILE_SOURCES: Final = (
    ("toml_file", TomlConfigSettingsSource),
    ("yaml_file", YamlConfigSettingsSource),
    ("json_file", JsonConfigSettingsSource),
)


class BaseSettings(SettingsBase):
    """Subclass and declare typed UPPERCASE fields; the constructor merges every layer in one pass.

    Complex values in env or .env are JSON-decoded; enums, paths and timedeltas validate on load, never at runtime.
    A `timedelta` reads ISO 8601 (`PT7S`) or `HH:MM:SS` from the environment."""

    model_config = SettingsConfigDict(
        frozen=True,
        ### the .env is the host's: ETRACK_* is ours and every other key is ignored — forbidding extras would make any
        ### foreign key (REDIS_URL, SECRET...) abort the load.
        extra="ignore",
        env_file=".env",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[SettingsBase],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        ### pydantic-settings reads these first-to-highest: kwargs beat env, the config file is the floor.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            *cls._settings_customise_files(settings_cls),
        )

    @staticmethod
    def _settings_customise_files(settings_cls: type[SettingsBase]) -> tuple[PydanticBaseSettingsSource, ...]:
        """The configured config-file sources only: absent format, absent source."""
        return tuple(source(settings_cls) for key, source in FILE_SOURCES if settings_cls.model_config.get(key))
