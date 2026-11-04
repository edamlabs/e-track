"""tests/integration/etrack/logic: the deep agent the viewer watches, the labels it declares and how long a read may wait."""

from typing import TYPE_CHECKING, Any

import pytest
from deepagents import create_deep_agent
from langchain_core.tools import tool

from support.model import call, script

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def wait() -> float:
    """Seconds a client or a stream may wait for the viewer."""
    return 20.0


@pytest.fixture
def viewer_labels() -> dict[str, str]:
    return {"PatchToolCallsMiddleware.before_agent": "Patch tool calls"}


@pytest.fixture
def deep_agent() -> Callable[[], Any]:
    """Builds a deep agent that delegates to a subagent, which calls an ontology tool."""

    @tool
    def onto_query(query: str) -> str:
        """Run a SPARQL query."""
        return "seg:Poliza"

    def build() -> Any:
        return create_deep_agent(
            model=script(
                call("task", "c1", subagent_type="ontologo", description="resolve Poliza"),
                call("onto_query", "c2", query="SELECT *"),
                "Poliza es seg:Poliza",
                "listo",
            ),
            subagents=[
                {"name": "ontologo", "description": "ontología", "system_prompt": "ontólogo", "tools": [onto_query]}
            ],
        )

    return build
