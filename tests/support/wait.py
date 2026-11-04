"""tests/support/wait: wait for a condition, never for a fixed time — a slow runner takes longer, never fails."""

from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from collections.abc import Callable

POLL = 0.01
LIMIT = 10.0


async def eventually(check: Callable[[], bool]) -> None:
    """Return as soon as `check()` holds; fail after `LIMIT` seconds."""
    with anyio.fail_after(LIMIT):
        while not check():  # noqa: ASYNC110 — the condition is a plain value a sink sets, there is nothing to await
            await anyio.sleep(POLL)
