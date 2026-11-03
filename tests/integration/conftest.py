"""tests/integration: the sandbox as session fixtures — `sandbox/compose.yml` up once per session, down when it ends.

pytest-docker owns the compose lifecycle (`up --build --wait`, `down -v`, a project named per process); these fixtures
point it at the sandbox, hand the collector a per-session output directory and the host's user, and wait until every
service answers. The tier is opt-in (`-m integration`): without docker it errors, it never skips in silence."""

import os
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from support.sandbox import Sandbox

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_docker.plugin import Services

COMPOSE: Final[Path] = Path(__file__).resolve().parents[2] / "sandbox" / "compose.yml"
BOOT: Final[float] = 120.0
PAUSE: Final[float] = 0.5


def _answering(url: str) -> bool:
    """Whether a service answers 200 on `url` yet."""
    try:
        with urllib.request.urlopen(url, timeout=1) as reply:  # noqa: S310 — a localhost URL the fixture built
            return reply.status == 200
    except OSError:
        return False


@pytest.fixture(scope="session")
def sandbox_out(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The collector's output directory for this session, and the variables compose interpolates."""
    out = tmp_path_factory.mktemp("sandbox")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SANDBOX_OUT", str(out))
        patch.setenv("SANDBOX_UID", str(os.getuid()))
        patch.setenv("SANDBOX_GID", str(os.getgid()))
        yield out


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return str(COMPOSE)


@pytest.fixture(scope="session")
def docker_setup(sandbox_out: Path) -> list[str]:
    """`up` runs only once the output directory and the host user are in the environment."""
    return ["up --build --wait"]


@pytest.fixture(scope="session")
def sandbox(docker_services: Services, docker_ip: str, sandbox_out: Path) -> Sandbox:
    """The running sandbox: every service answering, its endpoints on the ephemeral host ports compose chose."""
    collector = f"http://{docker_ip}:{docker_services.port_for('collector', 4318)}"
    health = f"http://{docker_ip}:{docker_services.port_for('collector', 13133)}/"
    phoenix = f"http://{docker_ip}:{docker_services.port_for('phoenix', 6006)}"
    docker_services.wait_until_responsive(lambda: _answering(health), timeout=BOOT, pause=PAUSE)
    docker_services.wait_until_responsive(lambda: _answering(f"{phoenix}/healthz"), timeout=BOOT, pause=PAUSE)
    return Sandbox(collector=collector, out=sandbox_out, phoenix=phoenix)
