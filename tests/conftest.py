"""tests: session-wide — nothing leaves the process: no ETRACK_* variable of the developer's shell reaches a test.

`Settings()` is read once, at import of `etrack.infra.settings`: the shell's ETRACK_* go before any test module
imports the library, so the defaults every provider fills are the fields' own. Each test still runs with them unset,
for the clusters it builds itself."""

import os

import pytest

### the integration tier reads where its collector is; nothing else of the shell reaches a test.
KEPT = "ETRACK_TEST_"


def foreign() -> list[str]:
    """The shell's ETRACK_* variables, the integration tier's own aside."""
    return [key for key in list(os.environ) if key.startswith("ETRACK_") and not key.startswith(KEPT)]


### at import, before any test module imports `etrack`: the one `Settings` is built on the fields' defaults.
_ = [os.environ.pop(key) for key in foreign()]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every ETRACK_* variable unset for the test: a cluster built here reads its defaults or what the test sets."""
    _ = [monkeypatch.delenv(key) for key in foreign()]
