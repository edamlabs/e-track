"""tests/unit/test_taxonomy: the import table, the framework fence and the shape of every provider, read on the tree.

Imports are read with `ast` (tach holds the layers too; this is the second, readable gate). The core — models, ports,
processors (layout aside), logic — never names a framework: each foreign library enters through the one module that
owns it. Every class that names itself a driver or an adapter declares its spec and lifecycle, lives at
`providers/<nature>/<capability>/<name>.py` where `<capability>` is a module of `ports/`, meets that port, agrees
with its locality (`EMBEDDED` is an adapter) and carries a unique `<Name><Nature>` name."""

import importlib
from collections import Counter
from typing import TYPE_CHECKING, get_protocol_members

import pytest

from etrack.ports.provider import Locality, Provider, ProviderSpec
from support.tree import (
    BRANDS,
    CASES,
    EVERY,
    FORBIDDEN,
    FRAMEWORKS,
    LIFECYCLE,
    PACKAGE,
    PORTS,
    PROVIDERS,
    dotted,
    layers,
    modules,
    names,
)

if TYPE_CHECKING:
    from pathlib import Path


##### THE IMPORT TABLE #####
@pytest.mark.parametrize(
    ("folder", "path"), CASES, ids=[f"{folder}:{path.relative_to(PACKAGE)}" for folder, path in CASES]
)
async def test_taxonomy_imports_obey_the_table(folder: str, path: Path) -> None:
    breaking = layers(path) & FORBIDDEN[folder]
    assert not breaking, f"{path.relative_to(PACKAGE)} imports {sorted(breaking)}, which a {folder} module may not"


##### THE FRAMEWORK FENCE #####
@pytest.mark.parametrize("path", EVERY, ids=[str(path.relative_to(PACKAGE)) for path in EVERY])
async def test_taxonomy_frameworks_enter_through_their_module(path: Path) -> None:
    relative = path.relative_to(PACKAGE).as_posix()
    spoken = {root for root in FRAMEWORKS for name in names(path) if name == root or name.startswith(f"{root}.")}
    trespassing = {root for root in spoken if relative not in FRAMEWORKS[root]}
    assert not trespassing, f"{relative} speaks {sorted(trespassing)}: only its owning module may"


##### PROVIDERS #####
async def test_taxonomy_every_provider_module_holds_one() -> None:
    held = {cls.__module__ for _, cls in PROVIDERS}
    assert held == {dotted(path) for folder in ("providers/drivers", "providers/adapters") for path in modules(folder)}


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_spec_lifecycle_locality(folder: str, cls: type) -> None:
    spec = getattr(cls, "spec", None)
    assert isinstance(spec, ProviderSpec), f"{cls.__name__} declares no ProviderSpec"
    assert all(callable(getattr(cls, name, None)) for name in LIFECYCLE), f"{cls.__name__} lacks part of the lifecycle"
    assert (spec.locality is Locality.EMBEDDED) is (folder == "providers/adapters")


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_meets_its_folder_port(folder: str, cls: type) -> None:
    capability = cls.__module__.split(".")[-2]
    assert capability in PORTS, f"{cls.__name__}: {capability!r} is no module of ports/"
    module = importlib.import_module(f"etrack.ports.{capability}")
    (port,) = (
        member
        for member in vars(module).values()
        if isinstance(member, type) and member.__module__ == module.__name__ and Provider in member.__mro__
    )
    missing = sorted(member for member in get_protocol_members(port) if not hasattr(cls, member))
    assert not missing, f"{cls.__name__} does not meet {port.__name__}: lacks {missing}"


async def test_taxonomy_provider_names_unique() -> None:
    assert not [name for name, count in Counter(cls.__name__ for _, cls in PROVIDERS).items() if count > 1]


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_carries_its_nature(folder: str, cls: type) -> None:
    assert cls.__name__.endswith(folder.removeprefix("providers/").title().removesuffix("s"))


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_name_is_brand_then_nature(folder: str, cls: type) -> None:
    *_, capability, brand = cls.__module__.split(".")
    nature = folder.removeprefix("providers/").title().removesuffix("s")
    ### the capability enters the name only when the brand repeats across capabilities: TeiEmbedDriver, TeiRerankDriver.
    qualifier = capability.title() if BRANDS[brand] > 1 else ""
    assert cls.__name__ == f"{brand.title()}{qualifier}{nature}"
