"""tests/unit/etrack/infra/settings: one `Settings` of category clusters — its sources, the library's root, the gates.

`infra/defaults` is the library's composition root: a provider takes keyword arguments and what it is not handed is
read there from `st`. The gates read the real `Settings` and the source tree: every field UPPERCASE, no field in two
clusters, the environment names held against the snapshot, `infra.settings` read only by the root, and nothing but
enums and value types taken from `infra.config` below it."""

import ast
import json
import re
from datetime import timedelta
from pathlib import Path
from types import UnionType
from typing import Final, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from etrack.infra import defaults
from etrack.infra import settings as composer
from etrack.infra.config.providers import ProviderSettings
from etrack.infra.settings import Settings, settings
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver

RESOURCES: Final[Path] = Path(__file__).resolve().parents[3] / "resources"
SNAPSHOT: Final[Path] = RESOURCES / "settings" / "env.json"
SOURCE: Final[Path] = Path(composer.__file__).resolve().parents[1]
CONFIG: Final[Path] = SOURCE / "infra" / "config"
### the composition root: entrypoints and the app they build, lifespans, deps, a cli's runtime — and, a library having
### none of them, its own `infra/defaults`.
ROOT: Final[re.Pattern[str]] = re.compile(
    r"(^|/)(main|__main__|app|deps|cli|lifespan)\.py$|(^|/)(lifespan|runtime)/|(^|/)infra/defaults\.py$"
)


##### SOURCES #####
def test_load_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRACK_BUS_CAPACITY", "7")
    monkeypatch.setenv("ETRACK_OTLP_TARGETS", '{"lf": {"endpoint": "http://x", "headers": {"A": "s"}}}')
    monkeypatch.setenv("ETRACK_OTLP_FLUSH", "PT2S")
    loaded = ProviderSettings()
    target = loaded.ETRACK_OTLP_TARGETS["lf"]
    assert (loaded.ETRACK_BUS_CAPACITY, target.endpoint, target.headers["A"].get_secret_value()) == (7, "http://x", "s")
    assert timedelta(seconds=2) == loaded.ETRACK_OTLP_FLUSH


def test_load_kwargs_beat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRACK_BUS_CAPACITY", "7")
    assert ProviderSettings(ETRACK_BUS_CAPACITY=3).ETRACK_BUS_CAPACITY == 3


def test_load_refuses_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ProviderSettings(ETRACK_SERVER_PORT=70000)


def test_frozen_blocks_mutation() -> None:
    with pytest.raises(ValidationError):
        settings.ETRACK_BUS_CAPACITY = 2


##### THE LIBRARY'S ROOT #####
def test_defaults_fill_what_is_not_given() -> None:
    conf = defaults.otlp(service="mine")
    assert (conf["service"], conf["traces"], conf["flush"]) == ("mine", True, settings.ETRACK_OTLP_FLUSH)


def test_defaults_refuse_a_value_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AnyioAdapter(capacity=0)


def test_a_provider_builds_with_no_argument() -> None:
    assert isinstance(OtlpDriver(), OtlpDriver)


def test_settings_is_one_instance_of_every_cluster() -> None:
    clusters = [base for base in Settings.__bases__ if issubclass(base, ProviderSettings.__mro__[1])]
    assert (isinstance(settings, Settings), len(clusters) == len(Settings.__bases__)) == (True, True)


##### GATES — the law, read from the tree #####
def structured(annotation: object) -> tuple[type[BaseModel], ...]:
    """The structured types `__` reaches into: the annotation itself, or a member of its union — never a container's."""
    kinds = get_args(annotation) if get_origin(annotation) in {Union, UnionType} else (annotation,)
    return tuple(kind for kind in kinds if isinstance(kind, type) and issubclass(kind, BaseModel))


def names(model: type[BaseModel]) -> set[str]:
    """The environment names a settings class reads: each field, and `FIELD__KEY` into a structured one."""
    nested = (
        f"{name}__{key.upper()}"
        for name, field in model.model_fields.items()
        for kind in structured(field.annotation)
        for key in kind.model_fields
    )
    return {*model.model_fields, *nested}


def test_every_field_is_uppercase() -> None:
    assert [name for name in Settings.model_fields if name != name.upper()] == []


def test_no_field_lives_in_two_clusters() -> None:
    owners = [name for base in Settings.__bases__ for name in base.__annotations__]
    assert sorted({name for name in owners if owners.count(name) > 1}) == []


def test_environment_names_are_held() -> None:
    assert sorted(names(Settings)) == json.loads(SNAPSHOT.read_text())


def imports(path: Path) -> list[tuple[str, str]]:
    """Every `from <module> import <name>` of a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.module or "", alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]


def below() -> list[Path]:
    """The modules below the composition root: every source module but the settings, the config and the root."""
    return [
        path
        for path in SOURCE.rglob("*.py")
        if CONFIG not in path.parents
        and path.name != "settings.py"
        and not ROOT.search(path.relative_to(SOURCE).as_posix())
    ]


def test_settings_is_read_by_the_composition_root_alone() -> None:
    readers = {
        path.relative_to(SOURCE).as_posix()
        for path in below()
        for module, _ in imports(path)
        if module.endswith("infra.settings")
    }
    assert sorted(readers) == []


def test_below_the_root_config_gives_only_types() -> None:
    clusters = {
        f"{path.relative_to(SOURCE).as_posix()}:{name}"
        for path in below()
        for module, name in imports(path)
        if ".infra.config" in f".{module}" and name.endswith("Settings")
    }
    assert sorted(clusters) == []
