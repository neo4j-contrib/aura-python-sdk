"""The HTTP transport interface.

A transport sends exactly one HTTP request and returns the response. Retries, authentication and
error mapping happen above it, so a custom transport only has to move bytes. Pass one to
``AuraClient(transport=...)`` to control proxies, TLS or connection handling, or to fake the network
in tests. This is the Python equivalent of the Go SDK's ``WithHTTPClient`` option.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """A single HTTP request to send.

    ``timeout`` is in seconds. A transport must not read more than ``max_response_size`` bytes
    of the response body. If the body is larger, it raises
    :class:`~aura_python_sdk.AuraResponseError`.
    """

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout: float
    max_response_size: int


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """The status, headers and fully read body of a response. Header names are lower-cased."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", {k.lower(): v for k, v in self.headers.items()})


@runtime_checkable
class HttpTransport(Protocol):
    """Sends HTTP requests.

    On a network failure, ``send`` raises :class:`~aura_python_sdk.AuraConnectionError`, or
    :class:`~aura_python_sdk.AuraTimeoutError` for timeouts. It sets ``request_sent=False`` only
    when it is certain the server never received the request. It returns non-2xx responses
    normally instead of raising.
    """

    def send(self, request: HttpRequest) -> HttpResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class AsyncHttpTransport(Protocol):
    """The async counterpart of :class:`HttpTransport`, for :class:`AsyncAuraClient`.

    ``send`` follows the same error rules as :meth:`HttpTransport.send`.
    """

    async def send(self, request: HttpRequest) -> HttpResponse: ...

    async def aclose(self) -> None: ...
