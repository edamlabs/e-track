"""processors/fold: FoldProcessor — a source's edges folded into ordered, parented, stamped RunEvents for one run.

A source reports every span it sees; the fold keeps the ones a person reads (an edge with a `kind`) and folds
plumbing (`kind=None`) into its nearest kept ancestor, so a frame's `parent` is always a span that was itself emitted.
It stamps what the source cannot know: the run's ids, `seq`, the `visit` count of each node, the latency of a closed
span, and the payload passed through the project's `redact`. The run's root closes with what the run declared (`declare`:
what entered, what it published), the attributes it was annotated with, and how it ended — failed, interrupted (an
interrupt was folded) or completed. With `propagate`, every frame carries the root's attributes (the host's `app.*`).
One fold per run; `emit` is whoever takes the frames."""

import itertools
import time
import uuid
from collections import Counter
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

import msgspec

from etrack.models.event import (
    EventKind,
    EventPhase,
    Failure,
    ModelRef,
    Outcome,
    Part,
    Pricer,
    Redact,
    RunEvent,
    RunScope,
    Usage,
)
from etrack.ports.source import Edge

type Emit = Callable[[RunEvent], None]

MS: Final[float] = 1000.0


@dataclass(frozen=True, slots=True)
class OpenSpan:
    """A kept span still running: the edge it opened with, its visible parent, its visit and when it began."""

    edge: Edge
    parent: str
    visit: int | None
    began: float


class FoldProcessor:
    """One run's edges as frames, pushed to `emit` the moment they are folded."""

    __slots__ = (
        "_annotated",
        "_carried",
        "_declared",
        "_emit",
        "_interrupted",
        "_open",
        "_pricer",
        "_propagate",
        "_redact",
        "_root",
        "_scope",
        "_seq",
        "_spans",
        "_spent",
        "_visits",
    )

    def __init__(
        self,
        scope: RunScope,
        emit: Emit,
        redact: Redact | None = None,
        *,
        propagate: bool = False,
        pricer: Pricer | None = None,
    ) -> None:
        self._scope = scope
        self._propagate = propagate
        self._pricer = pricer
        self._emit = emit
        self._redact = redact
        self._seq = itertools.count()
        self._root = ""
        ### every id seen → the span its children hang from: itself when kept, its kept ancestor when folded.
        self._spans: dict[str, str] = {}
        self._open: dict[str, OpenSpan] = {}
        self._visits: Counter[tuple[str, str]] = Counter()
        self._declared: dict[str, str] = {}
        self._interrupted = False
        ### the root's attributes every frame carries when propagating; what the run annotated, for its END.
        self._carried: dict[str, Any] = {}
        self._annotated: dict[str, Any] = {}
        ### what the model calls under each open NODE and RUN spent so far.
        self._spent: dict[str, Usage] = {}

    ##### PRIVATE #####

    def _common_visible(self, parent: str) -> str:
        return self._spans.get(parent, self._root if parent else "")

    def _common_visit(self, edge: Edge) -> int | None:
        ### a node is counted per mount: the same subgraph mounted twice counts its nodes apart (`ns` without task ids).
        match edge.kind:
            case EventKind.NODE:
                mount = "|".join(segment.partition(":")[0] for segment in edge.ns.split("|"))
                self._visits[mount, edge.name] += 1
                return self._visits[mount, edge.name]
            case _:
                return None

    def _common_frame(
        self,
        span: OpenSpan,
        phase: EventPhase,
        payload: dict[str, Any],
        **fields: Any,
    ) -> None:
        edge = span.edge
        event = RunEvent(
            run_id=self._scope.run_id,
            thread_id=self._scope.thread_id,
            seq=next(self._seq),
            id=edge.id,
            parent=span.parent,
            kind=edge.kind or EventKind.CUSTOM,
            phase=phase,
            name=edge.name,
            node=edge.node,
            ns=edge.ns,
            step=edge.step,
            visit=span.visit,
            ### an LLM call's message id is its span: every delta of one call belongs to one chat message.
            message_id=edge.message_id or (edge.id if edge.kind is EventKind.LLM else ""),
            call_id=fields.pop("call_id", "") or edge.call_id,
            model=edge.model,
            payload=payload,
            attributes={**self._carried, **edge.attributes, **fields.pop("attributes", {})},
            **fields,
        )
        self._emit(event if self._redact is None else event.masked(self._redact))

    def _close_spent(self, opened: OpenSpan, usage: Usage | None) -> Usage | None:
        ### a model call is priced and added to every NODE and RUN above it; a NODE or a RUN closes with its total.
        match (opened.edge.kind, usage):
            case (EventKind.LLM, Usage() as spent):
                priced = self._close_priced(opened, spent)
                _ = [self._close_add(above, priced) for above in self._close_above(opened.parent)]
                return priced
            case (EventKind.NODE | EventKind.RUN, None):
                return self._spent.pop(opened.edge.id, None)
            case _:
                return usage

    def _close_priced(self, opened: OpenSpan, usage: Usage) -> Usage:
        ### a cost the source already knows stands; the project's pricer fills the ones it does not.
        match self._pricer:
            case None:
                return usage
            case pricer:
                priced = usage.cost_usd is not None
                return (
                    usage
                    if priced
                    else msgspec.structs.replace(usage, cost_usd=pricer(opened.edge.model or ModelRef(), usage))
                )

    def _close_above(self, parent: str) -> list[str]:
        ### the open NODE and RUN spans from a span's parent up to the root.
        match self._open.get(parent):
            case OpenSpan(edge=edge, parent=up):
                here = [edge.id] if edge.kind in {EventKind.NODE, EventKind.RUN} else []
                return [*here, *self._close_above(up)]
            case _:
                return []

    def _close_add(self, span: str, usage: Usage) -> None:
        self._spent[span] = self._spent[span] + usage if span in self._spent else usage

    def _open_root(self, edge: Edge) -> None:
        ### the first kept span is the run's root: what it carries, every frame carries when propagating.
        match self._root:
            case "":
                self._root = edge.id
                self._carried = dict(edge.attributes) if self._propagate else {}
            case _:
                pass

    def _close_run(self, span: str, error: Failure | None) -> dict[str, Any]:
        ### only the root states what the run declared and how it ended.
        match span == self._root:
            case True:
                return {**self._declared, "outcome": self._close_outcome(error), "attributes": self._annotated}
            case _:
                return {}

    def _close_outcome(self, error: Failure | None) -> Outcome:
        match (error, self._interrupted):
            case (Failure(), _):
                return Outcome.FAILED
            case (None, True):
                return Outcome.INTERRUPTED
            case _:
                return Outcome.COMPLETED

    ############################################################

    ##### PUBLIC #####

    @property
    def scope(self) -> RunScope:
        """The run this fold stamps."""
        return self._scope

    @property
    def root(self) -> str:
        """The id of the run's root span, empty until the first kept span opens."""
        return self._root

    def open(self, edge: Edge) -> None:
        """A span begins: emitted when kept, folded into its ancestor when plumbing."""
        parent = self._common_visible(edge.parent)
        match edge.kind:
            case None:
                self._spans[edge.id] = parent
            case _:
                self._open_root(edge)
                span = OpenSpan(edge=edge, parent=parent, visit=self._common_visit(edge), began=time.perf_counter())
                self._spans[edge.id] = edge.id
                self._open[edge.id] = span
                self._common_frame(span, EventPhase.START, edge.payload)

    def delta(self, span: str, part: Part, payload: dict[str, Any], call_id: str = "") -> None:
        """A streamed piece of an open span; a piece of a span never opened, or already closed, is dropped."""
        match self._open.get(span):
            case OpenSpan() as opened:
                self._common_frame(opened, EventPhase.DELTA, payload, part=part, call_id=call_id)
            case _:
                pass

    def close(
        self, span: str, payload: dict[str, Any], usage: Usage | None = None, error: Failure | None = None
    ) -> None:
        """A span ends — END, or ERROR when it carries a failure; closing a folded or unknown span does nothing."""
        match self._open.pop(span, None):
            case OpenSpan() as opened:
                latency = round((time.perf_counter() - opened.began) * MS, 3)
                phase = EventPhase.END if error is None else EventPhase.ERROR
                run = self._close_run(span, error)
                spent = self._close_spent(opened, usage)
                self._common_frame(opened, phase, payload, latency_ms=latency, usage=spent, error=error, **run)
            case _:
                pass

    def instant(self, edge: Edge) -> None:
        """A frame born closed — an interrupt, a state, a score, a custom fact — under its visible parent."""
        parent = self._common_visible(edge.parent) if edge.parent else self._root
        self._interrupted = self._interrupted or edge.kind is EventKind.INTERRUPT
        ### a frame with no coordinates of its own stands where its parent runs.
        match (edge.node, self._open.get(parent)):
            case ("", OpenSpan(edge=around)):
                edge = msgspec.structs.replace(edge, node=around.node, ns=around.ns, step=around.step)
            case _:
                pass
        span = OpenSpan(edge=edge, parent=parent, visit=None, began=time.perf_counter())
        self._common_frame(span, EventPhase.INSTANT, edge.payload)

    def declare(self, input: str | None = None, output: str | None = None) -> None:  # noqa: A002 — the run's own word
        """What the run took in and what it published, as the code that said it states them; the root's END carries
        them. A word given again replaces the last; a word never given stays absent."""
        given = {key: text for key, text in (("input", input), ("output", output)) if text is not None}
        self._declared.update(given)

    def annotate(self, **attributes: Any) -> None:
        """Attributes learnt during the run — a verdict, a cut, a consent read late —, carried by the run's END."""
        self._annotated.update(attributes)

    @contextmanager
    def span(
        self,
        name: str,
        kind: EventKind = EventKind.CUSTOM,
        parent: str = "",
        payload: dict[str, Any] | None = None,
        **attributes: Any,
    ) -> Generator[str]:
        """A span around a block of the project's own code: START on entry, END or ERROR on exit; yields its id. Any
        other keyword is an attribute of the span — `run.fold.span("rank", tenant="acme", k=5)`."""
        span = uuid.uuid7().hex
        edge = Edge(
            id=span, parent=parent or self._root, kind=kind, name=name, payload=payload or {}, attributes=attributes
        )
        self.open(edge)
        try:
            yield span
        except BaseException as failure:
            self.close(span, {}, error=Failure(type=type(failure).__name__, message=str(failure)))
            raise
        self.close(span, {})
