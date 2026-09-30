"""Enforces that every third-party dependency is wrapped.

Each third-party package may be imported by exactly one internal module, and no public symbol may
expose a third-party type in its signature. Adding a dependency means registering its wrapper in
WRAPPED_DEPENDENCIES below.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
import typing
from collections.abc import Iterator
from pathlib import Path

import aura_python_sdk

PACKAGE = "aura_python_sdk"
SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
PACKAGE_ROOT = SRC_ROOT / PACKAGE

# third-party top-level module -> the single module (relative to src/) allowed to import it
WRAPPED_DEPENDENCIES: dict[str, str] = {
    "httpx": f"{PACKAGE}/_internal/http/_httpx.py",
}


def _source_files() -> Iterator[Path]:
    yield from sorted(PACKAGE_ROOT.rglob("*.py"))


def _imported_top_level_modules(path: Path) -> Iterator[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.split(".")[0]


def test_third_party_imports_are_confined_to_their_wrapper() -> None:
    violations: list[str] = []
    for path in _source_files():
        relative = path.relative_to(SRC_ROOT).as_posix()
        for lineno, module in _imported_top_level_modules(path):
            if module == PACKAGE or module in sys.stdlib_module_names:
                continue
            allowed = WRAPPED_DEPENDENCIES.get(module)
            if allowed is None:
                violations.append(
                    f"{relative}:{lineno} imports unregistered dependency {module!r}; "
                    "register a wrapper module in WRAPPED_DEPENDENCIES"
                )
            elif relative != allowed:
                violations.append(
                    f"{relative}:{lineno} imports {module!r}; only {allowed} may import it"
                )
    assert not violations, "\n".join(violations)


def _annotation_modules(annotation: object) -> Iterator[str]:
    module = getattr(annotation, "__module__", None)
    if isinstance(module, str):
        yield module
    for arg in typing.get_args(annotation):
        yield from _annotation_modules(arg)


def _public_signatures(obj: object) -> Iterator[tuple[str, object]]:
    """Yield (location, annotation) for every annotation reachable from a public symbol."""
    targets: list[tuple[str, object]] = []
    if inspect.isclass(obj):
        targets.append((obj.__qualname__, obj))
        if not dataclasses.is_dataclass(obj):
            targets.append((f"{obj.__qualname__}.__init__", obj.__init__))
        for name, member in inspect.getmembers(obj):
            if not name.startswith("_") and (
                inspect.isfunction(member) or isinstance(member, property)
            ):
                func = member.fget if isinstance(member, property) else member
                targets.append((f"{obj.__qualname__}.{name}", func))
    elif callable(obj):
        targets.append((getattr(obj, "__qualname__", repr(obj)), obj))

    for location, target in targets:
        try:
            hints = typing.get_type_hints(target)
        except TypeError:
            continue
        for hint in hints.values():
            yield location, hint


def test_public_api_does_not_expose_third_party_types() -> None:
    violations: list[str] = []
    for name in aura_python_sdk.__all__:
        for location, annotation in _public_signatures(getattr(aura_python_sdk, name)):
            for module in _annotation_modules(annotation):
                if module.split(".")[0] in WRAPPED_DEPENDENCIES:
                    violations.append(f"{location} exposes {module} type {annotation!r}")
    assert not violations, "\n".join(violations)
