"""Test doubles shared by the unit tests. No network access."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from aura_python_sdk import HttpRequest, HttpResponse

Reply = HttpResponse | Exception | Callable[[HttpRequest], HttpResponse]


def json_response(
    status_code: int, payload: object, headers: dict[str, str] | None = None
) -> HttpResponse:
    return HttpResponse(
        status_code=status_code,
        headers={"Content-Type": "application/json", **(headers or {})},
        body=json.dumps(payload).encode(),
    )


def token_response(
    access_token: str = "token-1", expires_in: int = 3600, token_type: str = "Bearer"
) -> HttpResponse:
    return json_response(
        200, {"access_token": access_token, "expires_in": expires_in, "token_type": token_type}
    )


@dataclass
class FakeClock:
    """A monotonic clock that only moves when told to; ``sleep`` advances it."""

    now: float = 1000.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport:
    """Replays queued replies in order and records every request."""

    def __init__(self, replies: Iterable[Reply] = ()) -> None:
        self.replies: deque[Reply] = deque(replies)
        self.requests: list[HttpRequest] = []
        self.closed = False

    def queue(self, *replies: Reply) -> None:
        self.replies.extend(replies)

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply(request)
        return reply

    def close(self) -> None:
        self.closed = True

    @property
    def api_requests(self) -> list[HttpRequest]:
        return [r for r in self.requests if not r.url.endswith("/oauth/token")]


class FakeAsyncTransport(FakeTransport):
    """The async counterpart of FakeTransport: same queue and recording, awaitable methods."""

    async def send(self, request: HttpRequest) -> HttpResponse:  # type: ignore[override]
        return FakeTransport.send(self, request)

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FakeAsyncSleep:
    """Advances a FakeClock instead of sleeping."""

    clock: FakeClock

    async def __call__(self, seconds: float) -> None:
        self.clock.sleep(seconds)
