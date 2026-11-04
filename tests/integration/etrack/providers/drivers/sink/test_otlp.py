"""tests/integration/etrack/providers/drivers/sink/otlp: a real deep-agent run, end to end, into the sandbox services.

The run goes source → fold → channel → bus → live + otlp; the session fixture brought the sandbox up. The collector
proves the wire — the span tree and the log records, read back from its OTLP/JSON files by the run's trace id; Phoenix
proves the dialect — the OpenInference kinds the driver writes, read back as Phoenix interprets them."""

from typing import TYPE_CHECKING

import pytest

from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.models.event import EventKind

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from integration.etrack.providers.drivers.sink.conftest import Run
    from support.sandbox import Sandbox

pytestmark = pytest.mark.integration


async def test_otlp_collector_receives_the_tree_and_its_logs(
    sandbox: Sandbox, deep_run: Callable[[OtlpSettings], Awaitable[Run]]
) -> None:
    run = await deep_run(
        OtlpSettings(targets={"collector": OtlpTarget(endpoint=sandbox.collector)}, logs=True, service="etrack-e2e")
    )
    spans = await sandbox.received("traces", run.trace, least=run.spans)
    assert len(spans) == run.spans
    assert {"ontologo", "onto_query"} <= {span["name"] for span in spans}
    ids = {span["spanId"] for span in spans}
    (root,) = [span for span in spans if not span.get("parentSpanId")]
    assert all(span["parentSpanId"] in ids for span in spans if span is not root)
    kinds = {
        attribute["value"]["stringValue"]
        for span in spans
        for attribute in span["attributes"]
        if attribute["key"] == "etrack.kind"
    }
    assert {str(EventKind.RUN), str(EventKind.SUBAGENT), str(EventKind.MCP), str(EventKind.LLM)} <= kinds
    logs = await sandbox.received("logs", run.trace, least=run.spans)
    assert len(logs) >= run.spans
    ### the live sink took every phase, deltas included.
    assert run.frames > run.spans


async def test_otlp_phoenix_reads_the_openinference_kinds(
    sandbox: Sandbox, deep_run: Callable[[OtlpSettings], Awaitable[Run]], project: str
) -> None:
    run = await deep_run(
        OtlpSettings(
            targets={"phoenix": OtlpTarget(endpoint=sandbox.phoenix)},
            service="etrack-e2e",
            attributes={"openinference.project.name": project},
        )
    )
    spans = await sandbox.spans(project, run.trace, least=run.spans)
    assert len(spans) == run.spans
    kinds = {span["name"]: span["span_kind"] for span in spans}
    assert kinds["ontologo"] == "AGENT"
    assert kinds["onto_query"] == "TOOL"
    assert "LLM" in kinds.values()
    ids = {span["context"]["span_id"] for span in spans}
    assert all(span["parent_id"] in ids for span in spans if span["parent_id"])
