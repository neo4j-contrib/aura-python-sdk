"""The async plumbing: retries, token sharing, 401 handling and client lifecycle."""

from __future__ import annotations

import asyncio
import logging

import pytest

import aura_python_sdk as aura
from aura_python_sdk import AuraConnectionError, HttpRequest, HttpResponse
from aura_python_sdk._internal._auth import AsyncTokenManager
from aura_python_sdk._internal.http._httpx import AsyncHttpxTransport
from aura_python_sdk._internal.http._service import AsyncHttpService
from tests.fakes import (
    FakeAsyncSleep,
    FakeAsyncTransport,
    FakeClock,
    FakeTransport,
    json_response,
    token_response,
)

URL = "https://api.neo4j.io/v1/instances"
pytestmark = pytest.mark.anyio


def _http(
    transport: FakeAsyncTransport, clock: FakeClock, max_retries: int = 3
) -> AsyncHttpService:
    return AsyncHttpService(
        transport,
        max_retries=max_retries,
        max_response_size=1024,
        logger=logging.getLogger("test"),
        clock=clock,
        sleep=FakeAsyncSleep(clock),
    )


async def test_retries_network_errors_with_backoff() -> None:
    clock = FakeClock()
    error = AuraConnectionError("reset", request_sent=True)
    transport = FakeAsyncTransport([error, error, HttpResponse(200)])
    response = await _http(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 60)
    assert response.status_code == 200
    assert clock.sleeps == [1.0, 2.0]


async def test_post_not_retried_once_sent() -> None:
    clock = FakeClock()
    transport = FakeAsyncTransport([AuraConnectionError("reset", request_sent=True)])
    with pytest.raises(AuraConnectionError):
        await _http(transport, clock).send("POST", URL, {}, b"{}", deadline=clock.now + 60)
    assert len(transport.requests) == 1


async def test_post_retried_when_never_sent() -> None:
    clock = FakeClock()
    transport = FakeAsyncTransport(
        [AuraConnectionError("refused", request_sent=False), HttpResponse(202)]
    )
    response = await _http(transport, clock).send("POST", URL, {}, b"{}", deadline=clock.now + 60)
    assert response.status_code == 202


async def test_deadline_stops_retries() -> None:
    clock = FakeClock()
    transport = FakeAsyncTransport([AuraConnectionError("refused", request_sent=False)])
    with pytest.raises(AuraConnectionError):
        await _http(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 0.5)
    assert clock.sleeps == []


async def test_expired_deadline() -> None:
    clock = FakeClock()
    with pytest.raises(aura.AuraTimeoutError):
        await _http(FakeAsyncTransport(), clock).send("GET", URL, {}, None, deadline=clock.now)


async def test_oversized_body_rejected() -> None:
    clock = FakeClock()
    transport = FakeAsyncTransport([HttpResponse(200, body=b"x" * 2000)])
    with pytest.raises(aura.AuraResponseError, match="exceeded limit"):
        await _http(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 5)


async def test_concurrent_tasks_share_one_token_fetch() -> None:
    fetches = 0

    class SlowTokenTransport(FakeAsyncTransport):
        async def send(self, request: HttpRequest) -> HttpResponse:  # type: ignore[override]
            nonlocal fetches
            fetches += 1
            await asyncio.sleep(0.02)
            return token_response("shared")

    clock = FakeClock()
    manager = AsyncTokenManager(
        client_id="id",
        client_secret="secret",
        token_url="https://api.neo4j.io/oauth/token",
        user_agent="ua",
        http=_http(SlowTokenTransport(), clock),
        logger=logging.getLogger("test"),
    )
    headers = await asyncio.gather(
        *(manager.authorization_header(deadline=clock.now + 30) for _ in range(10))
    )
    assert fetches == 1
    assert headers == ["Bearer shared"] * 10


async def test_token_refreshed_after_401() -> None:
    transport = FakeAsyncTransport(
        [
            token_response("old"),
            json_response(401, {"errors": [{"message": "expired"}]}),
            token_response("new"),
            json_response(200, {"data": []}),
        ]
    )
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    assert await client.tenants.list() == []
    assert [r.headers["Authorization"] for r in transport.api_requests] == [
        "Bearer old",
        "Bearer new",
    ]


async def test_rejected_credentials() -> None:
    transport = FakeAsyncTransport([json_response(401, {"error": "access_denied"})])
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    with pytest.raises(aura.AuthenticationError, match="access_denied"):
        await client.instances.list()


async def test_async_context_manager_closes_owned_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    async def fake_aclose(self: AsyncHttpxTransport) -> None:
        closed.append(True)

    monkeypatch.setattr(AsyncHttpxTransport, "aclose", fake_aclose)
    async with aura.AsyncAuraClient(client_id="id", client_secret="secret") as client:
        assert isinstance(client._transport, AsyncHttpxTransport)
    await client.aclose()  # idempotent
    assert closed == [True]


async def test_does_not_close_caller_transport() -> None:
    transport = FakeAsyncTransport()
    async with aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport):
        pass
    assert transport.closed is False


async def test_call_after_aclose_raises_client_closed() -> None:
    transport = FakeAsyncTransport()
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    await client.aclose()
    with pytest.raises(aura.AuraClientClosedError, match="client is closed"):
        await client.instances.list()
    assert transport.requests == []


def test_transport_kinds_are_not_interchangeable() -> None:
    with pytest.raises(aura.AuraConfigurationError, match="use AuraClient"):
        aura.AsyncAuraClient(client_id="id", client_secret="s", transport=FakeTransport())  # type: ignore[arg-type]
    with pytest.raises(aura.AuraConfigurationError, match="use AsyncAuraClient"):
        aura.AuraClient(client_id="id", client_secret="s", transport=FakeAsyncTransport())  # type: ignore[arg-type]
    with pytest.raises(aura.AuraConfigurationError, match="use AsyncAuraClient"):
        aura.AuraClient(client_id="id", client_secret="s", transport=AsyncHttpxTransport())  # type: ignore[arg-type]


def test_async_client_validates_options_like_sync() -> None:
    with pytest.raises(aura.AuraConfigurationError, match="HTTPS"):
        aura.AsyncAuraClient(client_id="id", client_secret="s", base_url="http://x")
    with pytest.raises(aura.AuraConfigurationError, match="logger"):
        aura.AsyncAuraClient(client_id="id", client_secret="s", logger="x")  # type: ignore[arg-type]


def test_async_from_env_and_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AURA_CLIENT_ID", "env-id")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "env-secret")
    client = aura.AsyncAuraClient.from_env(transport=FakeAsyncTransport(), timeout=5)
    assert repr(client) == "AsyncAuraClient(base_url='https://api.neo4j.io')"
    assert client.base_url == "https://api.neo4j.io"
    assert "env-secret" not in repr(client)
    monkeypatch.delenv("AURA_CLIENT_SECRET")
    with pytest.raises(aura.AuraConfigurationError, match="must both be set"):
        aura.AsyncAuraClient.from_env()


async def test_token_is_reused_across_calls() -> None:
    transport = FakeAsyncTransport(
        [token_response("tok"), json_response(200, {"data": []}), json_response(200, {"data": []})]
    )
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    await client.tenants.list()
    await client.tenants.list()
    assert [r.url.endswith("/oauth/token") for r in transport.requests] == [True, False, False]
