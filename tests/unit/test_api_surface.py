"""Freezes the SDK's public surface so it can only change on purpose.

Every exported class, enum, dataclass, function and service method is rendered into a flat text
snapshot (api_surface.txt) and compared against the version committed to the repo. A diff means
the public surface changed: review it, and if it's intentional, regenerate the snapshot with::

    AURA_UPDATE_SURFACE=1 pytest tests/unit/test_api_surface.py

This complements test_async_parity (sync/async method shape) and test_import_boundaries (no
third-party leakage): it's the one place that would also catch a renamed dataclass field, a
changed enum member, or a constructor signature change.
"""

from __future__ import annotations

import dataclasses
import enum
import inspect
import os
from pathlib import Path
from typing import Any

import aura_python_sdk as aura
from aura_python_sdk import services

SNAPSHOT_PATH = Path(__file__).parent / "api_surface.txt"

# (module, exported names) pairs that make up the public surface. Services aren't in
# aura_python_sdk.__all__ (they're only reachable as client.instances etc.) but their methods
# are just as public, so they're walked separately.
SURFACE_MODULES = [aura, services]

# Dunder methods worth tracking beyond __init__; everything else dunder is boilerplate.
_TRACKED_DUNDERS = {"__init__", "__enter__", "__exit__", "__aenter__", "__aexit__", "__call__"}


def _signature(func: Any) -> str:
    try:
        return str(inspect.signature(func))
    except (TypeError, ValueError):
        return "<unavailable>"


def _annotation_str(annotation: object) -> str:
    if annotation is inspect.Signature.empty:
        return "?"
    return annotation if isinstance(annotation, str) else inspect.formatannotation(annotation)


def _dataclass_lines(cls: type) -> list[str]:
    lines = []
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            default = repr(f.default)
        elif f.default_factory is not dataclasses.MISSING:
            default = f"factory:{f.default_factory!r}"
        else:
            default = "REQUIRED"
        lines.append(f"    {f.name}: {f.type} = {default}")
    return lines


def _enum_lines(cls: type[enum.Enum]) -> list[str]:
    return [f"    {member.name} = {member.value!r}" for member in cls]


def _public_methods(cls: type) -> list[str]:
    is_protocol = getattr(cls, "_is_protocol", False)
    lines = []
    for name, member in sorted(vars(cls).items()):
        if name.startswith("_") and name not in _TRACKED_DUNDERS:
            continue
        if name == "__init__" and is_protocol:
            continue  # synthetic Protocol.__init__, identical on every protocol
        if isinstance(member, (classmethod, staticmethod)):
            kind = "classmethod" if isinstance(member, classmethod) else "staticmethod"
            lines.append(f"    {kind} {name}{_signature(member.__func__)}")
        elif inspect.isfunction(member):
            lines.append(f"    {name}{_signature(member)}")
        elif isinstance(member, property):
            getter_sig = inspect.signature(member.fget) if member.fget else None
            returns = _annotation_str(getter_sig.return_annotation) if getter_sig else "?"
            lines.append(f"    property {name} -> {returns}")
    return lines


def _describe(obj: object) -> list[str]:
    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        return ["ENUM", *_enum_lines(obj)]
    if isinstance(obj, type):
        params: Any = getattr(obj, "__dataclass_params__", None)
        if params is not None:
            init = getattr(obj, "__init__")  # noqa: B009 - avoids mypy's static __init__ check
            header = f"DATACLASS(frozen={params.frozen}) __init__{_signature(init)}"
            return [header, *_dataclass_lines(obj)]
        bases = ", ".join(b.__name__ for b in obj.__bases__ if b is not object)
        header = f"CLASS({bases})" if bases else "CLASS"
        return [header, *_public_methods(obj)]
    if callable(obj):
        return [f"FUNCTION{_signature(obj)}"]
    return [f"VALUE = {obj!r}"]


def _surface() -> str:
    entries: dict[str, list[str]] = {}
    for module in SURFACE_MODULES:
        for name in module.__all__:
            qualified = f"{module.__name__}.{name}"
            entries[qualified] = _describe(getattr(module, name))
    lines = []
    for qualified in sorted(entries):
        lines.append(qualified)
        lines.extend(entries[qualified])
    text = "\n".join(lines) + "\n"
    # DEFAULT_USER_AGENT embeds __version__, which moves with every tag/dev build; pin it so the
    # snapshot reflects real surface changes, not which commit it was generated from.
    return text.replace(aura.__version__, "<version>")


def test_public_surface_matches_snapshot() -> None:
    current = _surface()
    if os.environ.get("AURA_UPDATE_SURFACE"):
        SNAPSHOT_PATH.write_text(current)
        return
    expected = SNAPSHOT_PATH.read_text()
    assert current == expected, (
        "The public API surface changed (see the diff above). If that's intentional, "
        "regenerate the snapshot with: AURA_UPDATE_SURFACE=1 pytest "
        f"{Path(__file__).relative_to(Path.cwd())}"
    )
