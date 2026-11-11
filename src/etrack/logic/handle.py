"""logic/handle: RunHandle — the run in progress, reached from anywhere inside it: span, fact, declare, annotate.

`Tracker.track` binds the run's fold in a context variable for its block; LangGraph runs its nodes, tools and
middlewares in copies of the caller's context, so the code the run calls reaches the fold without being handed it. A
span opened here hangs from what is running where it is opened — the node, the tool — as the source locates it. Outside
a run every call is a no-op: the same code runs tracked and untracked, and never fails for want of a tracker."""

import functools
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import msgspec

from etrack.infra.errors import FactError
from etrack.models.event import EventKind
from etrack.models.fact import FACT, LABELS, Fact
from etrack.ports.source import Edge

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from etrack.processors.fold import FoldProcessor


@dataclass(frozen=True, slots=True)
class Running:
    """The fold of the run in progress, and how its source tells which span is running where the caller stands."""

    fold: FoldProcessor
    locate: Callable[[], str]


RUNNING: ContextVar[Running | None] = ContextVar("etrack_running", default=None)
### the field types a label may have: a closed set of values, so a metric never grows a series per value.
CLOSED: Final[tuple[type, ...]] = (msgspec.inspect.EnumType, msgspec.inspect.BoolType, msgspec.inspect.LiteralType)


class RunHandle:
    """The run in progress, whoever calls: every method acts on the run bound in the caller's context, or does nothing."""

    __slots__ = ()

    ##### PRIVATE #####

    @staticmethod
    @functools.cache
    def _fact_labels(kind: type[Fact]) -> tuple[str, ...]:
        ### a class is read once: its labels must be fields, each of a closed type.
        fields = {field.name: msgspec.inspect.type_info(field.type) for field in msgspec.structs.fields(kind)}
        wrong = sorted(label for label in kind.labels if not isinstance(fields.get(label), CLOSED))
        match wrong:
            case []:
                return tuple(sorted(kind.labels))
            case _:
                msg = f"{kind.__name__}: labels {wrong} are not fields of a closed type (an enum, a bool, a Literal)"
                raise FactError(msg)

    @staticmethod
    def _fact_valid(value: Fact) -> dict[str, Any]:
        kind = type(value)
        try:
            return msgspec.to_builtins(msgspec.convert(msgspec.to_builtins(value), kind))
        except msgspec.ValidationError as failure:
            msg = f"{kind.__name__}: {failure}"
            raise FactError(msg) from failure

    ############################################################

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

    def fact(self, value: Fact) -> None:
        """A business event, validated against its class, as one frame under what is running; refused at the call when
        it does not meet its class, tracked or not."""
        kind = type(value)
        labels = self._fact_labels(kind)
        payload = self._fact_valid(value)
        match RUNNING.get():
            case Running(fold=fold, locate=locate):
                attributes = {FACT: kind.__name__, LABELS: list(labels)}
                edge = Edge(
                    id=uuid.uuid7().hex,
                    parent=locate(),
                    kind=EventKind.CUSTOM,
                    name=kind.__name__,
                    payload=payload,
                    attributes=attributes,
                )
                fold.instant(edge)
            case _:
                pass

    def declare(self, input: str | None = None, output: str | None = None) -> None:  # noqa: A002 — the run's own word
        """What the run took in, what it published: stated by the code that says it, carried on the run's END."""
        match RUNNING.get():
            case Running(fold=fold):
                fold.declare(input=input, output=output)
            case _:
                pass

    def annotate(self, **attributes: Any) -> None:
        """Attributes the run learnt on its way — a verdict, a cut, a consent —, carried by the run's END."""
        match RUNNING.get():
            case Running(fold=fold):
                fold.annotate(**attributes)
            case _:
                pass


run = RunHandle()
