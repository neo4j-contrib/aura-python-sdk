"""The default transport, backed by httpx.

This is the only module in the SDK that imports httpx (enforced by
tests/unit/test_import_boundaries.py). Every httpx type and exception is translated to the SDK's
own types at this boundary.
"""

from __future__ import annotations

import ssl

import httpx

from aura_python_sdk._errors import AuraConnectionError, AuraResponseError, AuraTimeoutError
from aura_python_sdk._transport import HttpRequest, HttpResponse

# Mirrors the Go SDK's http.Transport settings.
_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=90.0)

# httpx errors raised before any request bytes reach the server, so retrying cannot duplicate
# a mutation.
_NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _translate(exc: httpx.TransportError) -> AuraConnectionError:
    """Map an httpx network error to the SDK's own exception."""
    request_sent = not isinstance(exc, _NOT_SENT_ERRORS)
    if isinstance(exc, httpx.TimeoutException):
        return AuraTimeoutError(f"request timed out: {exc}", request_sent=request_sent)
    return AuraConnectionError(f"request failed: {exc}", request_sent=request_sent)


def _response(response: httpx.Response, body: bytes) -> HttpResponse:
    return HttpResponse(
        status_code=response.status_code, headers=dict(response.headers.items()), body=body
    )


def _too_large(limit: int) -> AuraResponseError:
    return AuraResponseError(f"response body exceeded limit of {limit} bytes")


class HttpxTransport:
    """An :class:`~aura_python_sdk.HttpTransport` backed by a pooled ``httpx.Client``."""

    def __init__(self, *, _httpx_transport: httpx.BaseTransport | None = None) -> None:
        # _httpx_transport is only for tests; it replaces the network layer below httpx.
        self._client = httpx.Client(
            verify=_tls_context(), limits=_LIMITS, follow_redirects=True, transport=_httpx_transport
        )

    def send(self, request: HttpRequest) -> HttpResponse:
        try:
            with self._client.stream(
                request.method,
                request.url,
                headers=dict(request.headers),
                content=request.body,
                timeout=httpx.Timeout(request.timeout),
            ) as response:
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > request.max_response_size:
                        raise _too_large(request.max_response_size)
                    chunks.append(chunk)
                return _response(response, b"".join(chunks))
        except httpx.TransportError as exc:
            raise _translate(exc) from exc

    def close(self) -> None:
        self._client.close()


class AsyncHttpxTransport:
    """An :class:`~aura_python_sdk.AsyncHttpTransport` backed by a pooled ``httpx.AsyncClient``."""

    def __init__(self, *, _httpx_transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            verify=_tls_context(), limits=_LIMITS, follow_redirects=True, transport=_httpx_transport
        )

    async def send(self, request: HttpRequest) -> HttpResponse:
        try:
            async with self._client.stream(
                request.method,
                request.url,
                headers=dict(request.headers),
                content=request.body,
                timeout=httpx.Timeout(request.timeout),
            ) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > request.max_response_size:
                        raise _too_large(request.max_response_size)
                    chunks.append(chunk)
                return _response(response, b"".join(chunks))
        except httpx.TransportError as exc:
            raise _translate(exc) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
