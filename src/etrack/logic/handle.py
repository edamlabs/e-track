"""logic/handle: RunHandle — the run in progress, reached from anywhere inside it: span, fact, annotate, declare.

`Tracker.track` binds the run's fold in a context variable for its block; LangGraph runs its nodes, tools and
middlewares in copies of the caller's context, so the code the run calls reaches the fold without being handed it. A
span opened here hangs from what is running where it is opened — the node, the tool — as the source locates it. Outside
a run every call is a no-op: the same code runs tracked and untracked, and never fails for want of a tracker."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from etrack.models.event import EventKind

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from etrack.processors.fold import FoldProcessor


@dataclass(frozen=True, slots=True)
class Running:
    """The fold of the run in progress, and how its source tells which span is running where the caller stands."""

    fold: FoldProcessor
    locate: Callable[[], str]


RUNNING: ContextVar[Running | None] = ContextVar("etrack_running", default=None)


class RunHandle:
    """The run in progress, whoever calls: every method acts on the run bound in the caller's context, or does nothing."""

    __slots__ = ()

    ##### PUBLIC #####

    @property
    def active(self) -> bool:
        """Whether the caller stands inside a tracked run."""
        return RUNNING.get() is not None

    @contextmanager
    def span(
        self, name: str, kind: EventKind = EventKind.CUSTOM, payload: dict[str, Any] | None = None, **attributes: Any
    ) -> Generator[str]:
        """A span around a block, under what is running where it opens; yields its id — empty outside a run."""
        match RUNNING.get():
            case Running(fold=fold, locate=locate):
                with fold.span(name, kind, parent=locate(), payload=payload, **attributes) as span:
                    yield span
            case _:
                yield ""


run = RunHandle()
