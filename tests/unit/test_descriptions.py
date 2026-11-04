"""tests/unit/test_descriptions: every module of etrack opens with one short sentence that starts with its path."""

import pytest

from support.tree import LIMIT, MODULES


@pytest.mark.parametrize(("relpath", "doc"), MODULES, ids=[name for name, _ in MODULES])
async def test_descriptions_module_prefixed(relpath: str, doc: str | None) -> None:
    assert doc, f"{relpath}: no docstring"
    first = doc.splitlines()[0].strip()
    assert first.startswith(f"{relpath}: "), f"{relpath}: top line must start with its path"
    assert first.endswith("."), f"{relpath}: top line must be one finished sentence"
    assert len(first) <= LIMIT, f"{relpath}: top description must stay short ({len(first)})"
