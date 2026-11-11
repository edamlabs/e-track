"""tests/unit/etrack/providers/adapters/outbox/sqlite: items stored once, leased, settled, given up and requeued."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from etrack.infra.errors import AdapterError
from etrack.ports.outbox import EntryState, OutboxPort
from etrack.providers.adapters.outbox.sqlite import SqliteAdapter

if TYPE_CHECKING:
    from pathlib import Path

LEASE = timedelta(minutes=5)


async def test_sqlite_meets_port(tmp_path: Path) -> None:
    async with SqliteAdapter(tmp_path / "outbox.db") as outbox:
        assert isinstance(outbox, OutboxPort)
        assert await outbox.health()
    assert not await outbox.health()


async def test_sqlite_closed(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="not open"):
        await SqliteAdapter(tmp_path / "outbox.db").append("k", b"{}")
    await SqliteAdapter(tmp_path / "outbox.db").__aexit__(None, None, None)


async def test_sqlite_append_once_claim_ack(tmp_path: Path) -> None:
    async with SqliteAdapter(tmp_path / "outbox.db") as outbox:
        assert [await outbox.append(key, b"1") for key in ("a", "b", "a")] == [True, True, False]
        claimed = await outbox.claim(10, LEASE)
        assert [(entry.key, entry.attempts, entry.state) for entry in claimed] == [
            ("a", 1, EntryState.PENDING),
            ("b", 1, EntryState.PENDING),
        ]
        ### leased: not due again until the lease ends.
        assert await outbox.claim(10, LEASE) == []
        await outbox.ack("a")
        assert await outbox.of("a") is None
        assert (await outbox.report())[EntryState.PENDING] == 1


async def test_sqlite_release_dead_requeue(tmp_path: Path) -> None:
    async with SqliteAdapter(tmp_path / "outbox.db") as outbox:
        await outbox.append("k", b"{}")
        await outbox.claim(1, LEASE)
        await outbox.release("k", datetime.now(UTC) - timedelta(seconds=1), "503 busy")
        (entry,) = await outbox.claim(1, LEASE)
        assert (entry.attempts, entry.reason) == (2, "503 busy")
        await outbox.dead("k", "422 bad")
        assert await outbox.claim(1, timedelta(0)) == []
        dead = await outbox.of("k")
        assert dead is not None
        assert (dead.state, dead.reason) == (EntryState.DEAD, "422 bad")
        assert dict(await outbox.report()) == {EntryState.PENDING: 0, EntryState.DEAD: 1}
        assert await outbox.requeue("k")
        assert not await outbox.requeue("k")
        (again,) = await outbox.claim(1, LEASE)
        assert (again.attempts, again.reason, again.state) == (1, "", EntryState.PENDING)


async def test_sqlite_survives_reopen(tmp_path: Path) -> None:
    async with SqliteAdapter(tmp_path / "outbox.db") as outbox:
        await outbox.append("k", b"kept")
    async with SqliteAdapter(tmp_path / "outbox.db") as outbox:
        (entry,) = await outbox.claim(1, LEASE)
    assert entry.item == b"kept"
