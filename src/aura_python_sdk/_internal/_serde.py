"""Conversion between JSON values and the SDK's dataclass models.

Field names match the JSON keys. Conversion is driven by each field's type hint:

- ``X | None`` fields accept a missing key or ``null``. Other fields without a default are
  required, and a missing key raises :class:`AuraResponseError`.
- ``SomeEnum | str`` fields hold the enum member when the value is known and the raw string
  otherwise, so a new status from the API never breaks parsing.
- Unknown JSON keys are ignored.
- Small spec inconsistencies are tolerated: a numeric string for an ``int`` field, or a number
  for a ``str`` field.
"""

from __future__ import annotations

import dataclasses
import re
import types
import typing
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar, cast

from aura_python_sdk._errors import AuraResponseError

T = TypeVar("T")

_NONE_TYPE = type(None)
# Python 3.11's fromisoformat accepts at most 6 fractional digits; the API (Go) may send 9.
_EXCESS_FRACTION = re.compile(r"(\.\d{6})\d+")


class _MismatchError(Exception):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path or '<root>'}: {message}")


def from_json(cls: type[T], value: object) -> T:
    """Build ``cls`` (a dataclass) from a decoded JSON value."""
    try:
        return cast(T, _convert(cls, value, ""))
    except _MismatchError as exc:
        raise AuraResponseError(f"unexpected response shape at {exc}") from None


def parse_data(cls: type[T], payload: object) -> T:
    """Unwrap a ``{"data": {...}}`` response into ``cls``."""
    return from_json(cls, _data(payload))


def parse_data_list(cls: type[T], payload: object) -> list[T]:
    """Unwrap a ``{"data": [...]}`` response into a list of ``cls``."""
    data = _data(payload)
    if not isinstance(data, list):
        raise AuraResponseError("unexpected response shape at data: expected a list")
    return [from_json(cls, item) for item in data]


def _data(payload: object) -> object:
    if not isinstance(payload, Mapping) or "data" not in payload:
        raise AuraResponseError("unexpected response shape: missing 'data'")
    return payload["data"]


_FieldSpec = tuple[str, Any, bool]
_FIELD_CACHE: dict[type[Any], tuple[_FieldSpec, ...]] = {}


def _fields(cls: type[Any]) -> tuple[_FieldSpec, ...]:
    """(name, resolved type, required) for each init field of a dataclass."""
    cached = _FIELD_CACHE.get(cls)
    if cached is None:
        hints = typing.get_type_hints(cls)
        cached = tuple(
            (
                f.name,
                hints[f.name],
                f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING,
            )
            for f in dataclasses.fields(cls)
            if f.init
        )
        _FIELD_CACHE[cls] = cached
    return cached


def _convert(tp: Any, value: object, path: str) -> object:
    origin = typing.get_origin(tp)

    if origin is typing.Union or origin is types.UnionType:
        return _convert_union(typing.get_args(tp), value, path)
    if value is None:
        raise _MismatchError(path, "value must not be null")
    if origin is tuple:
        item_type = typing.get_args(tp)[0]
        return tuple(
            _convert(item_type, v, f"{path}[{i}]") for i, v in enumerate(_list(value, path))
        )
    if origin is list:
        item_type = typing.get_args(tp)[0]
        return [_convert(item_type, v, f"{path}[{i}]") for i, v in enumerate(_list(value, path))]
    if dataclasses.is_dataclass(tp) and isinstance(tp, type):
        return _convert_dataclass(tp, value, path)
    if isinstance(tp, type) and issubclass(tp, Enum):
        try:
            return tp(value)
        except ValueError:
            raise _MismatchError(path, f"{value!r} is not a valid {tp.__name__}") from None
    if tp is bool:
        if isinstance(value, bool):
            return value
        raise _MismatchError(path, f"expected a boolean, got {value!r}")
    if tp is int:
        return _to_int(value, path)
    if tp is float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        raise _MismatchError(path, f"expected a number, got {value!r}")
    if tp is str:
        if isinstance(value, str):
            return value
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
        raise _MismatchError(path, f"expected a string, got {value!r}")
    if tp is datetime:
        return _to_datetime(value, path)
    if tp is date:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise _MismatchError(path, f"expected an ISO date, got {value!r}")
    raise TypeError(f"unsupported model field type {tp!r} at {path}")


def _convert_union(args: tuple[Any, ...], value: object, path: str) -> object:
    if value is None:
        if _NONE_TYPE in args:
            return None
        raise _MismatchError(path, "value must not be null")
    candidates = [a for a in args if a is not _NONE_TYPE]
    # Optional timestamps: treat an empty string like null.
    if value == "" and _NONE_TYPE in args and all(a in (datetime, date) for a in candidates):
        return None
    last_error: _MismatchError | None = None
    for candidate in candidates:
        try:
            return _convert(candidate, value, path)
        except _MismatchError as exc:
            last_error = exc
    raise last_error or _MismatchError(path, "no matching type")


def _convert_dataclass(cls: type[Any], value: object, path: str) -> object:
    if not isinstance(value, Mapping):
        raise _MismatchError(path, f"expected an object, got {type(value).__name__}")
    kwargs: dict[str, object] = {}
    for name, field_type, required in _fields(cls):
        field_path = f"{path}.{name}" if path else name
        if name in value:
            kwargs[name] = _convert(field_type, value[name], field_path)
        elif required:
            raise _MismatchError(field_path, "required field is missing")
    return cls(**kwargs)


def _list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise _MismatchError(path, f"expected a list, got {type(value).__name__}")
    return value


def _to_int(value: object, path: str) -> int:
    if isinstance(value, bool):
        raise _MismatchError(path, f"expected an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    raise _MismatchError(path, f"expected an integer, got {value!r}")


def _to_datetime(value: object, path: str) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(_EXCESS_FRACTION.sub(r"\1", value))
        except ValueError:
            pass
    raise _MismatchError(path, f"expected an ISO 8601 timestamp, got {value!r}")


def to_json(obj: object) -> object:
    """Convert a request model (or plain values) to JSON-ready data, omitting None fields."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_json(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
            if getattr(obj, f.name) is not None
        }
    if isinstance(obj, Mapping):
        return {str(k): to_json(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, list | tuple):
        return [to_json(v) for v in obj]
    return obj
