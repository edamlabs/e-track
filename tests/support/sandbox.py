"""tests/support/sandbox: the running sandbox as the tests see it — where to export, and what each service received.

The collector writes every export it takes as OTLP/JSON lines under `out`; Phoenix answers on its REST API. Both
take their time: a reader polls until the whole run shows up, or fails after `wait` seconds."""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import anyio

if TYPE_CHECKING:
    from pathlib import Path

PAUSE: Final[float] = 0.2
SIGNALS: Final[dict[str, tuple[str, str, str]]] = {
    "traces": ("traces.jsonl", "Spans", "spans"),
    "logs": ("logs.jsonl", "Logs", "logRecords"),
}


@dataclass(frozen=True, slots=True)
class Sandbox:
    """The services the session fixture brought up: the collector, its output, and Phoenix."""

    collector: str
    out: Path
    phoenix: str
    wait: float = 30.0

    ##### PRIVATE #####

    def _received_items(self, signal: str, trace: str) -> list[dict[str, Any]]:
        name, key, items = SIGNALS[signal]
        path = self.out / name
        lines = path.read_text("utf-8").splitlines() if path.exists() else []
        return [
            item
            for line in lines
            for resource in json.loads(line)[f"resource{key}"]
            for scope in resource[f"scope{key}"]
            for item in scope[items]
            if item.get("traceId") == trace
        ]

    def _phoenix_page(self, project: str, trace: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"trace_id": trace, "limit": 1000})
        url = f"{self.phoenix}/v1/projects/{project}/spans?{query}"
        try:
            with urllib.request.urlopen(url, timeout=5) as reply:  # noqa: S310 — a localhost URL the fixture built
                return json.loads(reply.read())["data"]
        except urllib.error.HTTPError as failure:
            ### the project exists once its first span lands: until then Phoenix answers 404.
            _ = failure.close()
            return []

    async def _common_poll(self, least: int, read: Any, *args: str) -> list[dict[str, Any]]:
        with anyio.fail_after(self.wait):
            ### each service ingests on its own clock: the read repeats until the whole run shows up.
            while len(found := await anyio.to_thread.run_sync(read, *args)) < least:  # noqa: ASYNC110 — a remote service signals nothing
                await anyio.sleep(PAUSE)
            return found

    ############################################################

    ##### PUBLIC #####

    async def received(self, signal: str, trace: str, least: int = 1) -> list[dict[str, Any]]:
        """Every span (`traces`) or log record (`logs`) of one trace the collector wrote, once `least` arrived."""
        return await self._common_poll(least, self._received_items, signal, trace)

    async def spans(self, project: str, trace: str, least: int = 1) -> list[dict[str, Any]]:
        """Every span of one trace as Phoenix stored it under `project`, once `least` arrived."""
        return await self._common_poll(least, self._phoenix_page, project, trace)
