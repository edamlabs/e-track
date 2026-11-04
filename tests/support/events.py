"""tests/support/events: a run's emitted frames read back — by kind and phase, by name, by lineage."""

from etrack.models.event import EventKind, EventPhase, RunEvent


def lineage(spans: dict[str, RunEvent], span: str) -> list[EventKind]:
    """The kinds from a span up to the root."""
    return [spans[span].kind, *lineage(spans, spans[span].parent)] if span else []


def kinds(emitted: list[RunEvent], phase: EventPhase = EventPhase.START) -> list[tuple[EventKind, str]]:
    """The kind and name of every frame of a phase, in order."""
    return [(event.kind, event.name) for event in emitted if event.phase is phase]


def by(emitted: list[RunEvent], kind: EventKind, phase: EventPhase) -> list[RunEvent]:
    """The frames of one kind in one phase, in order."""
    return [event for event in emitted if event.kind is kind and event.phase is phase]
