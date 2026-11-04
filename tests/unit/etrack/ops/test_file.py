"""tests/unit/etrack/ops/file: FileFinder — agnostic discovery over a package (the settings composer's engine)."""

import re
from typing import TYPE_CHECKING, Any, cast

import pytest

from etrack.infra import proxy
from etrack.infra.config.base import BaseSettings
from etrack.infra.errors import FileError
from etrack.ops.file import FileFinder, Kind

if TYPE_CHECKING:
    from pathlib import Path


async def test_file_modules_skip_packages(infra: FileFinder) -> None:
    assert {"errors", "logger", "proxy", "settings"} <= set(infra.discover(Kind.MODULES))
    assert "config" not in infra.discover(Kind.MODULES)


async def test_file_recursive_names_by_path(config: FileFinder) -> None:
    assert "providers.drivers.sink.otlp" in config.discover(Kind.MODULES)


async def test_file_classes_and_functions_own_only(infra: FileFinder) -> None:
    assert "LazyProxy" in infra.discover(Kind.CLASSES)
    assert "Any" not in infra.discover(Kind.CLASSES)
    assert FileFinder("etrack.ops").discover(Kind.FUNCTIONS).keys() >= {"w3c_trace", "w3c_span"}


async def test_file_base_and_pattern(config: FileFinder) -> None:
    found = config.discover(BaseSettings, pattern=re.compile(r"^Otlp"))
    assert set(found) == {"OtlpSettings"}
    assert "BaseSettings" not in config.discover(BaseSettings)


async def test_file_predicate_and_module(infra: FileFinder) -> None:
    assert set(infra.discover(proxy)) == {"LazyProxy"}
    assert "LazyProxy" in infra.discover(lambda obj: isinstance(obj, type) and obj.__name__.endswith("Proxy"))


async def test_file_rejects_target(infra: FileFinder) -> None:
    with pytest.raises(FileError, match="Unsupported discover target"):
        infra.discover(cast("Any", 42))


async def test_file_private_never_seen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pkgx").mkdir()
    (tmp_path / "pkgx" / "_hidden.py").write_text('"""h."""\nclass Hidden: ...\n')
    (tmp_path / "pkgx" / "shown.py").write_text('"""s."""\nclass Shown: ...\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    finder = FileFinder("pkgx")
    assert set(finder.discover(Kind.MODULES)) == {"shown"}
    assert finder.summaries() == {"shown": "s."}
    assert await finder.asummaries() == {"shown": "s."}
    assert set(await finder.adiscover(Kind.CLASSES)) == {"Shown"}
