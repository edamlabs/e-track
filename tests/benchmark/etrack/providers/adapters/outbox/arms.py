"""tests/benchmark/etrack/providers/adapters/outbox/arms: the outbox store's binding and durability, measured.

One append is one committed transaction. Four arms, interleaved round by round on a fresh file on the real disk: the
standard library's `sqlite3` on a worker thread (what `SqliteAdapter` runs) and aiosqlite, each with
`synchronous=FULL` and `NORMAL`. Not part of the suite — aiosqlite is no dependency. Run it from the repository root:

    uv run --with aiosqlite python tests/benchmark/etrack/providers/adapters/outbox/arms.py

Reported 2026-11-11 (`docs/decisions.md`): ext4 on NVMe, SQLite 3.50.4, aiosqlite 0.22.1, Python 3.14."""

import asyncio
import shutil
import statistics
import time
from pathlib import Path

import aiosqlite  # ty: ignore[unresolved-import]

from etrack.providers.adapters.outbox.sqlite import SqliteAdapter, Statement

ROOT = Path.home() / ".cache" / "etrack-bench"
ITEM = b'{"turn":"x"}'
COUNT, ROUNDS = 300, 5


async def stdlib(path: Path, sync: str) -> float:
    adapter = SqliteAdapter(path)
    await adapter.__aenter__()
    await adapter._common_run(lambda db: db.execute(f"PRAGMA synchronous={sync}"))
    began = time.perf_counter()
    _ = [await adapter.append(f"k{index}", ITEM) for index in range(COUNT)]
    spent = time.perf_counter() - began
    await adapter.__aexit__(None)
    return spent / COUNT * 1e3


async def aio(path: Path, sync: str) -> float:
    db = await aiosqlite.connect(path, isolation_level=None)
    await db.executescript(Statement.PRAGMAS)
    await db.execute(f"PRAGMA synchronous={sync}")
    await db.executescript(Statement.SCHEMA)
    began = time.perf_counter()
    _ = [await db.execute(Statement.APPEND, (f"k{index}", ITEM, 0.0, 0.0)) for index in range(COUNT)]
    spent = time.perf_counter() - began
    await db.close()
    return spent / COUNT * 1e3


ARMS = {
    "stdlib+thread FULL": (stdlib, "FULL"),
    "stdlib+thread NORMAL": (stdlib, "NORMAL"),
    "aiosqlite FULL": (aio, "FULL"),
    "aiosqlite NORMAL": (aio, "NORMAL"),
}


async def main() -> None:
    spent: dict[str, list[float]] = {name: [] for name in ARMS}
    for _ in range(ROUNDS):
        for name, (arm, sync) in ARMS.items():
            shutil.rmtree(ROOT, ignore_errors=True)
            ROOT.mkdir(parents=True)
            spent[name].append(await arm(ROOT / "outbox.db", sync))
    shutil.rmtree(ROOT, ignore_errors=True)
    _ = [
        print(f"{name:22s} median {statistics.median(times):.3f} ms/append  min {min(times):.3f}  max {max(times):.3f}")  # noqa: T201
        for name, times in spent.items()
    ]


if __name__ == "__main__":
    asyncio.run(main())
