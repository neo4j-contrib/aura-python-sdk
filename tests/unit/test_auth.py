import base64
import logging
import threading
import time
from urllib.parse import parse_qs

import pytest

from aura_python_sdk import (
    AuraResponseError,
    AuthenticationError,
    HttpRequest,
    HttpResponse,
    RateLimitError,
    ServerError,
)
from aura_python_sdk._internal._auth import TokenManager
from aura_python_sdk._internal.http._service import HttpService
from tests.fakes import FakeClock, FakeTransport, json_response, token_response

TOKEN_URL = "https://api.neo4j.io/oauth/token"


def _manager(transport: FakeTransport, clock: FakeClock | None = None) -> TokenManager:
    clock = clock or FakeClock()
    http = HttpService(
        transport,
        max_retries=0,
        max_response_size=1024,
        logger=logging.getLogger("test"),
        clock=clock,
        sleep=clock.sleep,
    )
    return TokenManager(
        client_id="my-id",
        client_secret="my-secret",
        token_url=TOKEN_URL,
        user_agent="ua/1",
        http=http,
        logger=logging.getLogger("test"),
    )


def _deadline() -> float:
    return float("inf")


def test_token_request_shape() -> None:
    transport = FakeTransport([token_response("abc")])
    header = _manager(transport).authorization_header(deadline=_deadline())

    assert header == "Bearer abc"
    [request] = transport.requests
    assert request.method == "POST"
    assert request.url == TOKEN_URL
    expected_basic = base64.b64encode(b"my-id:my-secret").decode()
    assert request.headers["Authorization"] == f"Basic {expected_basic}"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert request.headers["User-Agent"] == "ua/1"
    assert request.body is not None
    assert parse_qs(request.body.decode()) == {"grant_type": ["client_credentials"]}


def test_token_is_cached() -> None:
    transport = FakeTransport([token_response("abc")])
    manager = _manager(transport)
    for _ in range(3):
        assert manager.authorization_header(deadline=_deadline()) == "Bearer abc"
    assert len(transport.requests) == 1


def test_token_refreshed_sixty_seconds_before_expiry() -> None:
    clock = FakeClock()
    transport = FakeTransport([token_response("first", expires_in=3600), token_response("second")])
    manager = _manager(transport, clock)

    assert manager.authorization_header(deadline=_deadline()) == "Bearer first"
    clock.now += 3600 - 61
    assert manager.authorization_header(deadline=_deadline()) == "Bearer first"
    clock.now += 1
    assert manager.authorization_header(deadline=_deadline()) == "Bearer second"


def test_invalidate_forces_refetch() -> None:
    transport = FakeTransport([token_response("first"), token_response("second")])
    manager = _manager(transport)
    manager.authorization_header(deadline=_deadline())
    manager.invalidate()
    assert manager.authorization_header(deadline=_deadline()) == "Bearer second"


def test_lowercase_bearer_is_normalised() -> None:
    transport = FakeTransport([token_response("abc", token_type="bearer")])
    assert _manager(transport).authorization_header(deadline=_deadline()) == "Bearer abc"


@pytest.mark.parametrize("status", [400, 401, 403])
def test_client_errors_raise_authentication_error(status: int) -> None:
    body = {"errors": [{"message": "invalid client credentials", "reason": "invalid_client"}]}
    transport = FakeTransport([json_response(status, body)])
    with pytest.raises(AuthenticationError) as info:
        _manager(transport).authorization_header(deadline=_deadline())
    assert info.value.status_code == status
    assert info.value.details[0].reason == "invalid_client"


def test_rate_limit_and_server_errors_keep_their_type() -> None:
    transport = FakeTransport([HttpResponse(429), HttpResponse(503)])
    manager = _manager(transport)
    with pytest.raises(RateLimitError):
        manager.authorization_header(deadline=_deadline())
    with pytest.raises(ServerError):
        manager.authorization_header(deadline=_deadline())


@pytest.mark.parametrize(
    "payload",
    [
        {"access_token": "a", "expires_in": 3600, "token_type": "MAC"},
        {"access_token": "", "expires_in": 3600, "token_type": "Bearer"},
        {"access_token": "a", "expires_in": 0, "token_type": "Bearer"},
        {"access_token": "a", "expires_in": -5, "token_type": "Bearer"},
        {"access_token": "a", "expires_in": 86400 * 365 + 1, "token_type": "Bearer"},
        {"access_token": "a", "expires_in": "3600", "token_type": "Bearer"},
        {"access_token": "a", "expires_in": True, "token_type": "Bearer"},
        {"access_token": "a", "token_type": "Bearer"},
        ["not", "an", "object"],
    ],
)
def test_invalid_token_responses(payload: object) -> None:
    transport = FakeTransport([json_response(200, payload)])
    with pytest.raises(AuraResponseError):
        _manager(transport).authorization_header(deadline=_deadline())


def test_non_json_token_response() -> None:
    transport = FakeTransport([HttpResponse(200, body=b"<html>")])
    with pytest.raises(AuraResponseError):
        _manager(transport).authorization_header(deadline=_deadline())


def test_failed_fetch_does_not_cache() -> None:
    transport = FakeTransport([HttpResponse(503), token_response("ok")])
    manager = _manager(transport)
    with pytest.raises(ServerError):
        manager.authorization_header(deadline=_deadline())
    assert manager.authorization_header(deadline=_deadline()) == "Bearer ok"


def test_concurrent_callers_share_one_fetch() -> None:
    calls = 0

    def slow_token(request: HttpRequest) -> HttpResponse:
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return token_response("shared")

    transport = FakeTransport([slow_token])
    manager = _manager(transport)
    results: list[str] = []
    threads = [
        threading.Thread(
            target=lambda: results.append(manager.authorization_header(deadline=_deadline()))
        )
        for _ in range(10)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == 1
    assert results == ["Bearer shared"] * 10
