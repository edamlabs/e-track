"""models/fact: Fact — a business event as a typed value: its class names it, its fields type it, its labels count it.

A project subclasses `Fact` once per event it wants counted and kept (`BoundaryCrossed`, `HandedOver`): the subclass
name is the fact's schema name, its fields what it carries, and `labels` the fields a metric may be split by — closed
sets only (an enum, a bool, a `Literal`), so a label never explodes into a series per value. `run.fact(value)` emits it
as one frame under what is running, validated against its own class."""

from typing import ClassVar, Final

import msgspec

### the attributes a fact's frame carries: its schema name, and which of its fields are labels.
FACT: Final[str] = "etrack.fact"
LABELS: Final[str] = "etrack.fact.labels"


class Fact(msgspec.Struct, frozen=True, kw_only=True):
    """The base of every business event: subclass it, type its fields, name in `labels` the closed ones to count by."""

    labels: ClassVar[frozenset[str]] = frozenset()
