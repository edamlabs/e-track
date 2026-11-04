"""tests/support/sse: the Server-Sent Events wire as a test reads it — a stream's lines folded into messages."""

from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def sse(lines: AsyncIterator[str], count: int, within: float = 2.0) -> list[dict[str, Any]]:
    """The next `count` SSE messages of a stream's lines, each as its fields (`id`, `event`, `data` as sent)."""
    found: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    with anyio.fail_after(within):
        ### SSE is line-framed: a blank line closes a message.
        async for line in lines:
            match line.partition(": ") if line else ("", "", ""):
                case ("", _, _):
                    found += [current] if current else []
                    current = {}
                case (key, _, value):
                    current[key] = value
            if len(found) == count:
                break
    return found
