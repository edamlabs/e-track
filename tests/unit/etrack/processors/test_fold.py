"""tests/unit/etrack/processors/fold: edges folded into frames — parents, seq, visits, latency, redaction, spans."""

from typing import TYPE_CHECKING

import pytest

from etrack.models.event import (
    EventKind,
    EventPhase,
    Failure,
    ModelRef,
    Outcome,
    Part,
    Pricer,
    RunEvent,
    RunScope,
    Usage,
)
from etrack.ports.source import Edge, FoldPort
from etrack.processors.fold import FoldProcessor
from unit.etrack.conftest import RUN

if TYPE_CHECKING:
    from collections.abc import Callable


async def test_fold_meets_port(fold: FoldProcessor) -> None:
    assert isinstance(fold, FoldPort)


async def test_fold_root_and_scope(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge], scope: RunScope
) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    assert fold.root == "r"
    assert fold.scope is scope
    assert (emitted[0].run_id, emitted[0].thread_id, emitted[0].parent) == (RUN, "t1", "")


async def test_fold_plumbing_folds_into_ancestor(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]
) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("seq", "r", kind=None))
    fold.open(edge("n", "seq"))
    fold.close("seq", {})
    assert [event.id for event in emitted] == ["r", "n"]
    assert emitted[1].parent == "r"


async def test_fold_unknown_parent_hangs_from_root(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]
) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "never-seen"))
    assert emitted[1].parent == "r"


async def test_fold_seq_contiguous(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "r"))
    fold.delta("n", Part.TEXT, {"delta": "x"})
    fold.close("n", {})
    fold.close("r", {})
    assert [event.seq for event in emitted] == [0, 1, 2, 3, 4]


async def test_fold_visits_count_per_node(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]
) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    _ = [(fold.open(edge(f"a{index}", "r", name="agent")), fold.close(f"a{index}", {})) for index in range(3)]
    starts = [event.visit for event in emitted if event.phase is EventPhase.START and event.kind is EventKind.NODE]
    assert starts == [1, 2, 3]
    assert emitted[0].visit is None


async def test_fold_close_latency_usage(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]
) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.close("m", {"text": "hi"}, usage=Usage(input_tokens=2))
    end = emitted[-1]
    assert (end.phase, end.usage, end.payload) == (EventPhase.END, Usage(input_tokens=2), {"text": "hi"})
    assert end.latency_ms is not None
    assert end.latency_ms >= 0


async def test_fold_close_error(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("t", kind=EventKind.TOOL))
    fold.close("t", {}, error=Failure(type="ValueError", message="bad"))
    assert (emitted[-1].phase, emitted[-1].error) == (EventPhase.ERROR, Failure(type="ValueError", message="bad"))


@pytest.mark.parametrize("span", ["never", "closed"], ids=["unknown", "twice"])
async def test_fold_close_ignored(
    fold: FoldProcessor, emitted: list[RunEvent], span: str, edge: Callable[..., Edge]
) -> None:
    fold.open(edge("closed"))
    fold.close("closed", {})
    fold.close(span, {})
    assert len(emitted) == 2


async def test_fold_delta_closed_dropped(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]
) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.close("m", {})
    fold.delta("m", Part.TEXT, {"delta": "late"})
    assert len(emitted) == 2


async def test_fold_llm_message_id(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.delta("m", Part.TEXT, {"delta": "a"})
    fold.open(edge("t", kind=EventKind.TOOL, call_id="c1"))
    assert [event.message_id for event in emitted] == ["m", "m", ""]
    assert emitted[-1].call_id == "c1"


async def test_fold_delta_call_id(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.delta("m", Part.TOOL_CALL, {"delta": "{}"}, call_id="c9")
    assert (emitted[-1].part, emitted[-1].call_id) == (Part.TOOL_CALL, "c9")


async def test_fold_instant_parents(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "r"))
    fold.close("n", {})
    fold.instant(edge("i", "n", kind=EventKind.INTERRUPT))
    fold.instant(edge("s", kind=EventKind.STATE))
    assert [(event.phase, event.parent) for event in emitted[-2:]] == [
        (EventPhase.INSTANT, "n"),
        (EventPhase.INSTANT, "r"),
    ]


async def test_fold_redacts_every_payload(emitted: list[RunEvent], edge: Callable[..., Edge], scope: RunScope) -> None:
    fold = FoldProcessor(scope, emitted.append, redact=lambda payload: dict.fromkeys(payload, "***"))
    fold.open(edge("m", kind=EventKind.LLM, payload={"input": "secret"}))
    fold.delta("m", Part.TEXT, {"delta": "secret"})
    fold.close("m", {"text": "secret"})
    assert [event.payload for event in emitted] == [{"input": "***"}, {"delta": "***"}, {"text": "***"}]


async def test_fold_span_ok(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    with fold.span("gate", kind=EventKind.EVALUATION, payload={"rule": "shacl"}) as span:
        pass
    assert [(event.id, event.phase, event.parent) for event in emitted[1:]] == [
        (span, EventPhase.START, "r"),
        (span, EventPhase.END, "r"),
    ]
    assert emitted[1].payload == {"rule": "shacl"}


async def test_fold_span_error(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    msg = "boom"
    with pytest.raises(RuntimeError, match=msg), fold.span("work"):
        raise RuntimeError(msg)
    assert (emitted[-1].phase, emitted[-1].error) == (EventPhase.ERROR, Failure(type="RuntimeError", message=msg))


async def test_fold_own_span_extras(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    with fold.span("rank", tenant="acme", k=5):
        pass
    assert [(event.phase, event.attributes) for event in emitted] == [
        (EventPhase.START, {"tenant": "acme", "k": 5}),
        (EventPhase.END, {"tenant": "acme", "k": 5}),
    ]


##### DECLARED #####
async def test_fold_root_declares(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "r"))
    fold.declare(input="hola")
    fold.declare(output="borrador")
    fold.declare(output="respuesta")
    fold.close("n", {})
    fold.close("r", {})
    node, run = emitted[-2:]
    assert (node.input, node.output, node.outcome) == (None, None, None)
    assert (run.input, run.output, run.outcome) == ("hola", "respuesta", Outcome.COMPLETED)


async def test_fold_root_undeclared(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.close("r", {}, error=Failure(type="ValueError"))
    assert (emitted[-1].input, emitted[-1].output, emitted[-1].outcome) == (None, None, Outcome.FAILED)


async def test_fold_root_interrupted(fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.instant(edge("r:interrupt", "r", kind=EventKind.INTERRUPT))
    fold.close("r", {})
    assert emitted[-1].outcome is Outcome.INTERRUPTED


async def test_fold_declared_masked(scope: RunScope, edge: Callable[..., Edge]) -> None:
    emitted: list[RunEvent] = []
    fold = FoldProcessor(scope, emitted.append, lambda payload: {key: "***" for key in payload if key != "output"})
    fold.open(edge("r", kind=EventKind.RUN, payload={"a": 1}))
    fold.declare(input="secreto", output="se va")
    fold.close("r", {})
    assert (emitted[0].payload, emitted[-1].input, emitted[-1].output) == ({"a": "***"}, "***", None)


##### ATTRIBUTES #####
async def test_fold_annotated_on_root_end(
    fold: FoldProcessor, emitted: list[RunEvent], edge: Callable[..., Edge]
) -> None:
    fold.open(edge("r", kind=EventKind.RUN, attributes={"app.owner": "u1"}))
    fold.open(edge("n", "r"))
    fold.annotate(**{"app.cut": True})
    fold.close("n", {})
    fold.close("r", {})
    node, run = emitted[-2:]
    assert node.attributes == {}
    assert run.attributes == {"app.owner": "u1", "app.cut": True}


async def test_fold_propagates_root(scope: RunScope, edge: Callable[..., Edge]) -> None:
    emitted: list[RunEvent] = []
    fold = FoldProcessor(scope, emitted.append, propagate=True)
    fold.open(edge("r", kind=EventKind.RUN, attributes={"app.owner": "u1"}))
    fold.open(edge("n", "r", attributes={"own": 1}))
    fold.instant(edge("i", "n", kind=EventKind.CUSTOM))
    fold.close("n", {})
    assert [event.attributes for event in emitted] == [
        {"app.owner": "u1"},
        {"app.owner": "u1", "own": 1},
        {"app.owner": "u1"},
        {"app.owner": "u1", "own": 1},
    ]


##### COST #####
def _spend(fold: FoldProcessor, edge: Callable[..., Edge], span: str, parent: str, tokens: int) -> None:
    fold.open(edge(span, parent, kind=EventKind.LLM, model=ModelRef(name="gemini")))
    fold.close(span, {}, usage=Usage(input_tokens=tokens, output_tokens=1, total_tokens=tokens + 1))


@pytest.mark.parametrize(("pricer", "cost"), [(None, None), (lambda model, usage: usage.input_tokens / 100, 0.6)])
async def test_fold_usage_rolls_up(
    scope: RunScope, edge: Callable[..., Edge], pricer: Pricer | None, cost: float | None
) -> None:
    emitted: list[RunEvent] = []
    fold = FoldProcessor(scope, emitted.append, pricer=pricer)
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("a", "r"))
    _spend(fold, edge, "m1", "a", 10)
    fold.open(edge("t", "a", kind=EventKind.TOOL))
    _spend(fold, edge, "m2", "t", 20)
    fold.close("t", {})
    fold.close("a", {})
    fold.open(edge("b", "r"))
    _spend(fold, edge, "m3", "b", 30)
    fold.close("b", {})
    fold.open(edge("idle", "r"))
    fold.close("idle", {})
    fold.close("r", {})
    ended = {event.id: usage for event in emitted if event.phase is EventPhase.END and (usage := event.usage)}
    assert (ended["a"].input_tokens, ended["b"].input_tokens, ended["r"].input_tokens) == (30, 30, 60)
    assert (ended["r"].output_tokens, ended["r"].total_tokens) == (3, 63)
    assert sorted(ended) == ["a", "b", "m1", "m2", "m3", "r"]
    assert ended["r"].cost_usd == pytest.approx(cost)
    assert sum(ended[call].cost_usd or 0 for call in ("m1", "m2", "m3")) == pytest.approx(cost or 0)


async def test_fold_source_cost_kept(scope: RunScope, edge: Callable[..., Edge]) -> None:
    emitted: list[RunEvent] = []
    fold = FoldProcessor(scope, emitted.append, pricer=lambda model, usage: 9.0)
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("m", "r", kind=EventKind.LLM))
    fold.close("m", {}, usage=Usage(input_tokens=1, cost_usd=0.25))
    fold.close("r", {})
    assert [usage.cost_usd for event in emitted if (usage := event.usage)] == [0.25, 0.25]


async def test_usage_sum_cost_unknown() -> None:
    assert (Usage(input_tokens=1) + Usage(input_tokens=2)).cost_usd is None
    assert (Usage(cost_usd=0.5) + Usage()).cost_usd == 0.5
