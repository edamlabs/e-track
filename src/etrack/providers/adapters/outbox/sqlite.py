"""providers/adapters/outbox/sqlite: SqliteAdapter — the outbox in one SQLite file, on the standard library.

One table, one row per undelivered item: `append` inserts once per key (a key already there is not appended again),
`claim` leases what is due in one statement, `ack` deletes, `release` and `dead` settle, `requeue` gives a dead item a
fresh deadline. The connection is the process's own, in WAL mode with `synchronous=FULL`: a committed append survives a
killed process and a lost machine alike. Every call runs on a worker thread, one at a time, so the loop never waits on
the disk."""

import asyncio
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Self

from etrack.infra.errors import AdapterError
from etrack.infra.logger import logger
from etrack.ports.outbox import Entry, EntryState
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from datetime import timedelta
    from pathlib import Path


class Statement(StrEnum):
    """Every statement the adapter runs: the outbox's whole SQL, in one place."""

    PRAGMAS = "PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;"
    SCHEMA = (
        "CREATE TABLE IF NOT EXISTS outbox (key TEXT PRIMARY KEY, item BLOB NOT NULL, state TEXT NOT NULL,"
        " attempts INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, due REAL NOT NULL, reason TEXT NOT NULL"
        " DEFAULT ''); CREATE INDEX IF NOT EXISTS outbox_due ON outbox (state, due);"
    )
    APPEND = (
        "INSERT INTO outbox (key, item, state, created, due) VALUES (?, ?, 'pending', ?, ?)"
        " ON CONFLICT (key) DO NOTHING"
    )
    CLAIM = (
        "UPDATE outbox SET due = ?, attempts = attempts + 1 WHERE key IN (SELECT key FROM outbox"
        " WHERE state = 'pending' AND due <= ? ORDER BY due LIMIT ?)"
        " RETURNING key, item, state, attempts, created, due, reason"
    )
    ACK = "DELETE FROM outbox WHERE key = ?"
    RELEASE = "UPDATE outbox SET due = ?, reason = ? WHERE key = ?"
    DEAD = "UPDATE outbox SET state = 'dead', reason = ? WHERE key = ?"
    OF = "SELECT key, item, state, attempts, created, due, reason FROM outbox WHERE key = ?"
    REQUEUE = (
        "UPDATE outbox SET state = 'pending', attempts = 0, created = ?, due = ?, reason = ''"
        " WHERE key = ? AND state = 'dead'"
    )
    REPORT = "SELECT state, count(*) FROM outbox GROUP BY state"


type Row = tuple[str, bytes, str, int, float, float, str]


class SqliteAdapter:
    """The outbox in a SQLite file: durable on commit, read and written off the loop, one call at a time."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("sqlite", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.THREAD)

    __slots__ = ("_db", "_lock", "_path")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._db: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    ##### PRIVATE #####

    @staticmethod
    def _common_now() -> float:
        return datetime.now(UTC).timestamp()

    @staticmethod
    def _common_entry(row: Row) -> Entry:
        key, item, state, attempts, created, due, reason = row
        return Entry(
            key=key,
            item=item,
            state=EntryState(state),
            attempts=attempts,
            created=datetime.fromtimestamp(created, UTC),
            due=datetime.fromtimestamp(due, UTC),
            reason=reason,
        )

    def _common_db(self) -> sqlite3.Connection:
        match self._db:
            case sqlite3.Connection() as db:
                return db
            case _:
                msg = "SqliteAdapter is not open: the lifespan opens it before a sink appends"
                raise AdapterError(msg)

    async def _common_run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        db = self._common_db()
        async with self._lock:
            return await asyncio.to_thread(work, db)

    @staticmethod
    def _enter_connect(path: Path) -> sqlite3.Connection:
        db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        db.executescript(Statement.PRAGMAS)
        db.executescript(Statement.SCHEMA)
        return db

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._db = await asyncio.to_thread(self._enter_connect, self._path)
        logger.info("outbox opened", outbox=self.spec.name, path=str(self._path))
        return self

    async def __aexit__(self, *exc: object) -> None:
        db, self._db = self._db, None
        _ = db and await asyncio.to_thread(db.close)
        logger.info("outbox closed", outbox=self.spec.name)

    async def health(self) -> bool:
        """Open, and its file answers."""
        try:
            await self._common_run(lambda db: db.execute("SELECT 1").fetchone())
        except AdapterError, sqlite3.Error:
            return False
        return True

    async def append(self, key: str, item: bytes) -> bool:
        """The item stored under `key`, due now; `False` when the key is already there (nothing is appended twice)."""
        now = self._common_now()
        return await self._common_run(lambda db: db.execute(Statement.APPEND, (key, item, now, now)).rowcount == 1)

    async def claim(self, limit: int, lease: timedelta) -> Sequence[Entry]:
        """Up to `limit` due items, the oldest first, each leased for `lease` and counted as one more attempt."""
        now = self._common_now()
        until = now + lease.total_seconds()
        rows = await self._common_run(lambda db: db.execute(Statement.CLAIM, (until, now, limit)).fetchall())
        return sorted((self._common_entry(row) for row in rows), key=lambda entry: entry.created)

    async def ack(self, key: str) -> None:
        """Delivered: the item leaves the outbox."""
        await self._common_run(lambda db: db.execute(Statement.ACK, (key,)))

    async def release(self, key: str, due: datetime, reason: str) -> None:
        """Not delivered this time: due again at `due`, with why."""
        await self._common_run(lambda db: db.execute(Statement.RELEASE, (due.timestamp(), reason, key)))

    async def dead(self, key: str, reason: str) -> None:
        """Given up, with why: kept, never claimed again unless requeued."""
        await self._common_run(lambda db: db.execute(Statement.DEAD, (reason, key)))

    async def of(self, key: str) -> Entry | None:
        """The item under `key` while it is undelivered; `None` once delivered or never appended."""
        row = await self._common_run(lambda db: db.execute(Statement.OF, (key,)).fetchone())
        return self._common_entry(row) if row else None

    async def requeue(self, key: str) -> bool:
        """A dead item due again now, its attempts and its deadline started afresh; `False` when it is not dead."""
        now = self._common_now()
        return await self._common_run(lambda db: db.execute(Statement.REQUEUE, (now, now, key)).rowcount == 1)

    async def report(self) -> Mapping[EntryState, int]:
        """How many items are pending and dead."""
        rows = await self._common_run(lambda db: db.execute(Statement.REPORT).fetchall())
        counted = {EntryState(state): count for state, count in rows}
        return MappingProxyType({state: counted.get(state, 0) for state in EntryState})
