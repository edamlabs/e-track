"""tests/unit/etrack/ops: finders over the infra packages, and a run id whose hex is known."""

import pytest

from etrack.ops.file import FileFinder


@pytest.fixture
def infra() -> FileFinder:
    return FileFinder("etrack.infra")


@pytest.fixture
def config() -> FileFinder:
    return FileFinder("etrack.infra.config", recursive=True)


@pytest.fixture
def run() -> str:
    return "019a" + "0" * 12 + "8" + "f" * 15
