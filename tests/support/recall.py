"""tests/support/recall: a custom driver built on HttpDriver — what a memory service recording recall would receive."""

from typing import Any

import msgspec

from etrack.models.event import EventKind, EventPhase, EventView
from etrack.providers.drivers.sink.http import HttpDriver


class Recall(EventView, frozen=True, kw_only=True):
    """What a memory service keeps of a retrieval."""

    run_id: str
    kind: EventKind
    phase: EventPhase
    name: str = ""
    payload: dict[str, Any] = msgspec.field(default_factory=dict)


class RecallDriver(HttpDriver):
    """Retrievals only, each shaped as the memory service's recall record, one JSON body per batch."""

    view = Recall
    phases = frozenset({EventPhase.END})

    def accept(self, view: EventView) -> bool:
        return isinstance(view, Recall) and view.kind is EventKind.RETRIEVAL

    def encode(self, view: EventView) -> Any:
        recall = msgspec.convert(msgspec.to_builtins(view), Recall)
        return {"run": recall.run_id, "query": recall.name, "hits": recall.payload.get("hits", [])}

    def body(self, items: Any) -> tuple[bytes, str]:
        return msgspec.json.encode({"recalls": items}), "application/json"
