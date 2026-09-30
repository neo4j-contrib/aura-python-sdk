"""Polling a resource until an asynchronous operation finishes, shared by sync and async services.

``Target`` says what finished and failed look like. ``wait`` and ``async_wait`` are the same
loop around a sync or async fetch: fetch, check, sleep for ``interval`` (never past the
timeout), repeat.

A resource that was just created can briefly return 404, so a ``NotFoundError`` within
``NOT_FOUND_GRACE`` seconds of the start counts as "not visible yet". After that it is raised,
so waiting on a wrong ID fails in a minute rather than at the timeout.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Generic, TypeVar

from aura_python_sdk._errors import (
    AuraValidationError,
    NotFoundError,
    OperationFailedError,
    WaitTimeoutError,
)

T = TypeVar("T")

DEFAULT_WAIT_TIMEOUT = 900.0
DEFAULT_WAIT_INTERVAL = 10.0
NOT_FOUND_GRACE = 60.0


@dataclass(frozen=True, slots=True)
class Target(Generic[T]):
    """``describe`` completes "waiting for ...", e.g. "instance abc to be running"."""

    describe: str
    status: Callable[[T], object]
    done: object
    failed: Collection[object]

    def check(self, resource: T) -> bool:
        """True when finished; raises OperationFailedError on a failed state."""
        status = self.status(resource)
        if status == self.done:
            return True
        if status in self.failed:
            raise OperationFailedError(
                f"stopped waiting for {self.describe}: status is {status}", resource=resource
            )
        return False


def validate_wait(timeout: float, interval: float) -> tuple[float, float]:
    for name, value in (("timeout", timeout), ("interval", interval)):
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise AuraValidationError(
                f"{name} must be a finite number of seconds greater than zero"
            )
    return float(timeout), float(interval)


def _pause(
    target: Target[T], resource: T | None, deadline: float, now: float, interval: float
) -> float:
    remaining = deadline - now
    if remaining <= 0:
        state = "not found" if resource is None else f"status is {target.status(resource)}"
        raise WaitTimeoutError(
            f"timed out waiting for {target.describe}: {state}", resource=resource
        )
    return min(interval, remaining)


def _tolerate(exc: NotFoundError, start: float, now: float) -> None:
    if now - start > NOT_FOUND_GRACE:
        raise exc


def wait(
    fetch: Callable[[], T],
    target: Target[T],
    *,
    timeout: float,
    interval: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> T:
    start = clock()
    deadline = start + timeout
    while True:
        resource: T | None
        try:
            resource = fetch()
        except NotFoundError as exc:
            _tolerate(exc, start, clock())
            resource = None
        if resource is not None and target.check(resource):
            return resource
        sleep(_pause(target, resource, deadline, clock(), interval))


async def async_wait(
    fetch: Callable[[], Awaitable[T]],
    target: Target[T],
    *,
    timeout: float,
    interval: float,
    clock: Callable[[], float],
    sleep: Callable[[float], Awaitable[None]],
) -> T:
    start = clock()
    deadline = start + timeout
    while True:
        resource: T | None
        try:
            resource = await fetch()
        except NotFoundError as exc:
            _tolerate(exc, start, clock())
            resource = None
        if resource is not None and target.check(resource):
            return resource
        await sleep(_pause(target, resource, deadline, clock(), interval))
