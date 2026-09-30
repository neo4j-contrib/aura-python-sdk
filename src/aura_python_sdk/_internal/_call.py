"""A description of one API call, shared by the sync and async services.

Each service operation validates its arguments and returns a ``Call``, without doing any I/O.
The sync and async services then run the same ``Call`` through their own request service, so
validation, paths, bodies and parsing are written once.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from aura_python_sdk._internal._request import ApiResponse, QueryParams
from aura_python_sdk._internal._serde import parse_data, parse_data_list

T = TypeVar("T")


@dataclass(frozen=True, slots=True, kw_only=True)
class Call(Generic[T]):
    method: str
    path: str
    parse: Callable[[ApiResponse], T]
    params: QueryParams | None = None
    json_body: object = None
    # Logged at DEBUG before sending.
    describe: str
    # Logged at INFO after success. Used for operations that change something.
    done: str | None = None
    context: Mapping[str, object] = field(default_factory=dict)


def one(cls: type[T]) -> Callable[[ApiResponse], T]:
    """Parse ``{"data": {...}}`` into ``cls``."""
    return lambda response: parse_data(cls, response.json())


def many(cls: type[T]) -> Callable[[ApiResponse], list[T]]:
    """Parse ``{"data": [...]}`` into a list of ``cls``."""
    return lambda response: parse_data_list(cls, response.json())


def nothing(response: ApiResponse) -> None:
    """For endpoints that return no body (204)."""
