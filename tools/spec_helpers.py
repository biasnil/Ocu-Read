"""Helpers used by ocuread.spec (kept here so they can be tested outside a full build).

PaddleX, transformers and friends check their own dependencies at run time with
``importlib.metadata`` (``requires()`` / ``version()``). PyInstaller only bundles a package's metadata
(its ``*.dist-info`` folder) if asked, so in a frozen app those checks fail with errors such as
"`OCR` requires additional dependencies". The functions below find *every* package the given
distributions depend on - including the optional extras such as ``paddlex[ocr]`` - so their metadata
can be bundled without maintaining a hand-written list.
"""
from __future__ import annotations

import importlib.util
from importlib import metadata
from pathlib import Path
from typing import Iterable

from packaging.requirements import Requirement


def requirement_names(dist: str, extras: Iterable[str] = ()) -> list[tuple[str, tuple[str, ...]]]:
    """Direct requirements of ``dist`` (with the given extras enabled) as ``(name, child_extras)`` pairs."""
    try:
        raw_requirements = metadata.requires(dist) or []
    except metadata.PackageNotFoundError:
        return []
    active = ("",) + tuple(extras)
    found: list[tuple[str, tuple[str, ...]]] = []
    for raw in raw_requirements:
        req = Requirement(raw)
        if req.marker is None or any(req.marker.evaluate({"extra": e}) for e in active):
            found.append((req.name, tuple(req.extras)))
    return found


def dependency_closure(roots: dict[str, tuple[str, ...]]) -> list[str]:
    """Every installed distribution reachable from ``roots`` ({name: extras}), roots included."""
    seen: set[str] = set()
    order: list[str] = []
    queue: list[tuple[str, tuple[str, ...]]] = list(roots.items())
    while queue:
        name, extras = queue.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue                      # optional dependency that isn't installed
        seen.add(key)
        order.append(name)
        queue.extend(requirement_names(name, extras))
    return order


def top_level_modules(dists: Iterable[str]) -> list[str]:
    """Importable top-level module names provided by the given distributions."""
    wanted = {d.lower().replace("_", "-") for d in dists}
    modules: list[str] = []
    for module, providers in metadata.packages_distributions().items():
        if any(p.lower().replace("_", "-") in wanted for p in providers) and not module.startswith("_"):
            modules.append(module)
    return sorted(set(modules))


NATIVE_SUFFIXES = (".pyd", ".dll", ".so", ".dylib")


def native_libraries(package: str) -> list[tuple[str, str]]:
    """``(source, destination_dir)`` for every native library inside an installed package.

    Some packages load a compiled library *by file path* instead of importing it - torchvision looks for
    ``torchvision/_C.pyd`` next to itself and silently carries on without its custom ops if the file is
    missing (later surfacing as "operator torchvision::nms does not exist"). PyInstaller only bundles
    native files it finds through imports, so these must be added explicitly, keeping the folder layout.
    """
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        return []
    root = Path(next(iter(spec.submodule_search_locations)))
    found: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix.lower() in NATIVE_SUFFIXES or ".so." in path.name):
            found.append((str(path), str(Path(package) / path.parent.relative_to(root))))
    return found
