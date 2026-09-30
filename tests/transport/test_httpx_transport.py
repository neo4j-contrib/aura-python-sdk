"""HttpxTransport against httpx.MockTransport (tests may import httpx; src may not)."""

import ssl
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from aura_python_sdk import (
    AuraConnectionError,
    AuraResponseError,
    AuraTimeoutError,
    HttpRequest,
    HttpTransport,
)
from aura_python_sdk._internal.http._httpx import HttpxTransport


def _request(**overrides: object) -> HttpRequest:
    values: dict[str, object] = {
        "method": "POST",
        "url": "https://api.neo4j.io/v1/instances",
        "headers": {"Authorization": "Bearer t", "Content-Type": "application/json"},
        "body": b'{"name":"x"}',
        "timeout": 12.5,
        "max_response_size": 1024,
    }
    values.update(overrides)
    return HttpRequest(**values)  # type: ignore[arg-type]


def _transport(handler: object) -> HttpxTransport:
    return HttpxTransport(_httpx_transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_satisfies_protocol() -> None:
    assert isinstance(HttpxTransport(), HttpTransport)


def test_request_and_response_are_translated() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, headers={"X-Request-Id": "r1"}, content=b'{"data":{}}')

    response = _transport(handler).send(_request())

    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.neo4j.io/v1/instances"
    assert request.headers["authorization"] == "Bearer t"
    assert request.content == b'{"name":"x"}'
    assert request.extensions["timeout"] == {
        "connect": 12.5,
        "read": 12.5,
        "write": 12.5,
        "pool": 12.5,
    }
    assert response.status_code == 202
    assert response.headers["x-request-id"] == "r1"
    assert response.body == b'{"data":{}}'


def test_error_statuses_are_returned_not_raised() -> None:
    response = _transport(lambda r: httpx.Response(500, content=b"boom")).send(_request())
    assert response.status_code == 500
    assert response.body == b"boom"


def test_body_over_limit_is_rejected_while_streaming() -> None:
    chunks_read = 0

    def stream() -> Iterator[bytes]:
        nonlocal chunks_read
        for _ in range(100):
            chunks_read += 1
            yield b"x" * 512

    handler = lambda r: httpx.Response(200, content=stream())  # noqa: E731
    with pytest.raises(AuraResponseError, match="exceeded limit"):
        _transport(handler).send(_request(max_response_size=1024))
    assert chunks_read < 100


def test_body_at_limit_is_accepted() -> None:
    response = _transport(lambda r: httpx.Response(200, content=b"x" * 1024)).send(_request())
    assert len(response.body) == 1024


def test_redirects_are_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/old":
            return httpx.Response(308, headers={"Location": "https://api.neo4j.io/v1/new"})
        return httpx.Response(200, content=b"moved")

    response = _transport(handler).send(
        _request(method="GET", body=None, url="https://api.neo4j.io/v1/old")
    )
    assert response.body == b"moved"


@pytest.mark.parametrize(
    ("exc", "expected_type", "request_sent"),
    [
        (httpx.ConnectError("refused"), AuraConnectionError, False),
        (httpx.ConnectTimeout("slow connect"), AuraTimeoutError, False),
        (httpx.PoolTimeout("pool"), AuraTimeoutError, False),
        (httpx.ReadTimeout("slow read"), AuraTimeoutError, True),
        (httpx.WriteTimeout("slow write"), AuraTimeoutError, True),
        (httpx.ReadError("reset"), AuraConnectionError, True),
        (httpx.RemoteProtocolError("bad"), AuraConnectionError, True),
    ],
)
def test_network_errors_are_translated(
    exc: Exception, expected_type: type[AuraConnectionError], request_sent: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    with pytest.raises(expected_type) as info:
        _transport(handler).send(_request())
    assert type(info.value) is expected_type
    assert info.value.request_sent is request_sent
    assert isinstance(info.value.__cause__, httpx.HTTPError)


def test_tls_minimum_is_1_2() -> None:
    transport = HttpxTransport()
    pool = transport._client._transport._pool  # type: ignore[attr-defined]
    context: ssl.SSLContext = pool._ssl_context
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert context.verify_mode == ssl.CERT_REQUIRED
    transport.close()


# --- AsyncHttpxTransport ---

from aura_python_sdk import AsyncHttpTransport  # noqa: E402
from aura_python_sdk._internal.http._httpx import AsyncHttpxTransport  # noqa: E402


def _async_transport(handler: object) -> AsyncHttpxTransport:
    return AsyncHttpxTransport(_httpx_transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_async_satisfies_protocol() -> None:
    assert isinstance(AsyncHttpxTransport(), AsyncHttpTransport)


@pytest.mark.anyio
async def test_async_request_and_response_are_translated() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, headers={"X-Request-Id": "r1"}, content=b'{"data":{}}')

    transport = _async_transport(handler)
    response = await transport.send(_request())
    await transport.aclose()

    [request] = seen
    assert request.method == "POST"
    assert request.headers["authorization"] == "Bearer t"
    assert request.content == b'{"name":"x"}'
    assert response.status_code == 202
    assert response.headers["x-request-id"] == "r1"
    assert response.body == b'{"data":{}}'


@pytest.mark.anyio
async def test_async_body_over_limit_is_rejected() -> None:
    async def stream() -> AsyncIterator[bytes]:
        for _ in range(100):
            yield b"x" * 512

    handler = lambda r: httpx.Response(200, content=stream())  # noqa: E731
    with pytest.raises(AuraResponseError, match="exceeded limit"):
        await _async_transport(handler).send(_request(max_response_size=1024))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exc", "expected_type", "request_sent"),
    [
        (httpx.ConnectError("refused"), AuraConnectionError, False),
        (httpx.ReadTimeout("slow read"), AuraTimeoutError, True),
        (httpx.PoolTimeout("pool"), AuraTimeoutError, False),
        (httpx.RemoteProtocolError("bad"), AuraConnectionError, True),
    ],
)
async def test_async_network_errors_are_translated(
    exc: Exception, expected_type: type[AuraConnectionError], request_sent: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    with pytest.raises(expected_type) as info:
        await _async_transport(handler).send(_request())
    assert type(info.value) is expected_type
    assert info.value.request_sent is request_sent
