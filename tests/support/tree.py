"""tests/support/tree: the source tree read at collection — modules, imports, providers, config — for the structure tests.

Everything here is computed once, on import, so the structure tests parametrize over it: the event loop does no file
I/O. `FORBIDDEN` and `FRAMEWORKS` are the rules the tree is held to; the rest is what the tree says."""

import ast
import importlib
from collections import Counter
from pathlib import Path
from typing import Final

PACKAGE: Final = Path(__file__).resolve().parents[2] / "src" / "etrack"
CONFIG: Final = PACKAGE / "infra" / "config"
LIMIT: Final = 120
LIFECYCLE: Final = ("__aenter__", "__aexit__", "health")
FORBIDDEN: Final[dict[str, frozenset[str]]] = {
    "models": frozenset({"ports", "providers", "processors", "logic", "infra", "api"}),
    "ports": frozenset({"providers", "processors", "logic", "api"}),
    "providers/drivers": frozenset({"providers", "processors", "logic", "api"}),
    "providers/adapters": frozenset({"providers", "processors", "logic", "api"}),
    "processors": frozenset({"providers", "logic", "api"}),
    "api": frozenset({"providers", "processors", "logic"}),
    "logic": frozenset({"providers"}),
    "infra": frozenset({"ports", "providers", "processors", "logic", "models", "api"}),
    "ops": frozenset({"ports", "providers", "processors", "logic", "models", "api"}),
}
FRAMEWORKS: Final[dict[str, frozenset[str]]] = {
    "langchain_core": frozenset({"providers/adapters/source/langgraph.py"}),
    "langgraph": frozenset({"providers/adapters/source/langgraph.py", "providers/adapters/topology/langgraph.py"}),
    "opentelemetry": frozenset({"providers/drivers/sink/otlp.py"}),
    "rustworkx": frozenset({"processors/layout.py"}),
    "eserde": frozenset({"providers/drivers/sink/otlp.py", "api/viewer.py"}),
    "litestar": frozenset({"api/viewer.py"}),
    "granian": frozenset({"providers/adapters/server/granian.py"}),
}


def modules(folder: str) -> list[Path]:
    """Every module under a folder of the package, sorted."""
    return sorted(path for path in (PACKAGE / folder).rglob("*.py") if "__pycache__" not in path.parts)


def dotted(path: Path) -> str:
    """The importable name of a module of the package."""
    return "etrack." + path.relative_to(PACKAGE).with_suffix("").as_posix().replace("/", ".")


def names(path: Path) -> set[str]:
    """Every module a file imports, read with `ast`."""
    nodes = list(ast.walk(ast.parse(path.read_text("utf-8"))))
    named = {node.module for node in nodes if isinstance(node, ast.ImportFrom) and node.module}
    return named | {alias.name for node in nodes if isinstance(node, ast.Import) for alias in node.names}


def layers(path: Path) -> set[str]:
    """The layers of the package a file imports."""
    return {name.split(".")[1] for name in names(path) if name.startswith("etrack.")}


def providers() -> list[tuple[str, type]]:
    """Every driver and adapter class, with the folder it lives in."""
    layout = (("providers/drivers", "Driver"), ("providers/adapters", "Adapter"))
    found = [
        (folder, surname, importlib.import_module(dotted(path)))
        for folder, surname in layout
        for path in modules(folder)
    ]
    return [
        (folder, cls)
        for folder, surname, module in found
        for name, cls in vars(module).items()
        if isinstance(cls, type) and name.endswith(surname) and cls.__module__ == module.__name__
    ]


CASES: Final = [(folder, path) for folder in FORBIDDEN for path in modules(folder)]
EVERY: Final = modules(".")
PROVIDERS: Final = providers()
PORTS: Final = frozenset(path.stem for path in modules("ports")) - {"provider"}
BRANDS: Final = Counter(cls.__module__.split(".")[-1] for _, cls in PROVIDERS)
CONFIGS: Final = sorted((CONFIG / "providers").rglob("*.py"))
MODULES: Final = [
    (path.relative_to(PACKAGE).with_suffix("").as_posix(), ast.get_docstring(ast.parse(path.read_text("utf-8"))))
    for path in sorted(PACKAGE.rglob("*.py"))
    if "__pycache__" not in path.parts
]
