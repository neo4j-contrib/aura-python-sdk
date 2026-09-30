"""Retries and response limits on top of a transport (Go: internal/httpclient).

The retry policy is written once, as pure functions. ``HttpService`` and ``AsyncHttpService`` are
thin loops around it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping

from aura_python_sdk._errors import (
    AuraConnectionError,
    AuraResponseError,
    AuraTimeoutError,
    parse_retry_after,
)
from aura_python_sdk._transport import AsyncHttpTransport, HttpRequest, HttpResponse, HttpTransport

# Methods that are safe to repeat when the server may already have received the request.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

# Responses that mean "try again shortly": rate limited, or a gateway or service unavailable.
# Retried only for idempotent methods. A plain 500 may mean the request was acted on, so it isn't.
_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

RETRY_WAIT_MIN = 1.0
RETRY_WAIT_MAX = 5.0


class _RetryPolicy:
    """Retries with exponential backoff (1 s doubling to 5 s), never past the deadline.

    Network failures are retried, but if the request may have reached the server, only for
    idempotent methods, so a ``POST /instances`` is never sent twice. A 429, 502, 503 or 504 is
    retried for idempotent methods only, waiting ``Retry-After`` when the server sends it. Any
    other response is final. Both kinds of retry share ``max_retries``.
    """

    def __init__(
        self,
        *,
        max_retries: int,
        max_response_size: int,
        logger: logging.Logger,
        clock: Callable[[], float],
    ) -> None:
        self.max_retries = max_retries
        self.max_response_size = max_response_size
        self.logger = logger
        self.clock = clock

    def build_request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        deadline: float,
    ) -> HttpRequest:
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise AuraTimeoutError("request deadline exceeded", request_sent=False)
        self.logger.debug("sending HTTP request", extra={"method": method, "url": url})
        return HttpRequest(
            method=method,
            url=url,
            headers=headers,
            body=body,
            timeout=remaining,
            max_response_size=self.max_response_size,
        )

    def retry_wait(
        self, method: str, url: str, exc: AuraConnectionError, attempt: int, deadline: float
    ) -> float | None:
        """Seconds to wait before retrying, or None to give up and re-raise."""
        wait = _backoff(attempt)
        retryable = not exc.request_sent or method.upper() in _IDEMPOTENT_METHODS
        if attempt >= self.max_retries or not retryable or self.clock() + wait >= deadline:
            return None
        self.logger.debug(
            "retrying HTTP request after network error",
            extra={"method": method, "url": url, "attempt": attempt + 1, "error": str(exc)},
        )
        return wait

    def status_retry_wait(
        self, method: str, url: str, response: HttpResponse, attempt: int, deadline: float
    ) -> float | None:
        """Seconds to wait before retrying this response, or None to return it."""
        if (
            response.status_code not in _RETRYABLE_STATUSES
            or method.upper() not in _IDEMPOTENT_METHODS
            or attempt >= self.max_retries
        ):
            return None
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        wait = _backoff(attempt) if retry_after is None else retry_after
        if self.clock() + wait >= deadline:
            # Waiting would pass the deadline; the caller gets the error (with retry_after).
            return None
        self.logger.debug(
            "retrying HTTP request after retryable status",
            extra={
                "method": method,
                "url": url,
                "attempt": attempt + 1,
                "status": response.status_code,
                "wait": wait,
            },
        )
        return wait

    def check_response(self, method: str, url: str, response: HttpResponse) -> HttpResponse:
        if len(response.body) > self.max_response_size:
            raise AuraResponseError(
                f"response body exceeded limit of {self.max_response_size} bytes"
            )
        self.logger.debug(
            "HTTP response received",
            extra={"method": method, "url": url, "status": response.status_code},
        )
        return response


def _backoff(attempt: int) -> float:
    return min(RETRY_WAIT_MAX, RETRY_WAIT_MIN * 2.0**attempt)


class HttpService:
    """Sends requests through a sync transport with the shared retry policy."""

    def __init__(
        self,
        transport: HttpTransport,
        *,
        max_retries: int,
        max_response_size: int,
        logger: logging.Logger,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._policy = _RetryPolicy(
            max_retries=max_retries, max_response_size=max_response_size, logger=logger, clock=clock
        )
        self._sleep = sleep

    @property
    def clock(self) -> Callable[[], float]:
        return self._policy.clock

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        deadline: float,
    ) -> HttpResponse:
        attempt = 0
        while True:
            request = self._policy.build_request(method, url, headers, body, deadline)
            try:
                response = self._transport.send(request)
            except AuraConnectionError as exc:
                wait = self._policy.retry_wait(method, url, exc, attempt, deadline)
                if wait is None:
                    raise
                self._sleep(wait)
                attempt += 1
                continue
            response = self._policy.check_response(method, url, response)
            wait = self._policy.status_retry_wait(method, url, response, attempt, deadline)
            if wait is None:
                return response
            self._sleep(wait)
            attempt += 1


class AsyncHttpService:
    """Sends requests through an async transport with the shared retry policy."""

    def __init__(
        self,
        transport: AsyncHttpTransport,
        *,
        max_retries: int,
        max_response_size: int,
        logger: logging.Logger,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transport = transport
        self._policy = _RetryPolicy(
            max_retries=max_retries, max_response_size=max_response_size, logger=logger, clock=clock
        )
        self._sleep = sleep

    @property
    def clock(self) -> Callable[[], float]:
        return self._policy.clock

    async def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        deadline: float,
    ) -> HttpResponse:
        attempt = 0
        while True:
            request = self._policy.build_request(method, url, headers, body, deadline)
            try:
                response = await self._transport.send(request)
            except AuraConnectionError as exc:
                wait = self._policy.retry_wait(method, url, exc, attempt, deadline)
                if wait is None:
                    raise
                await self._sleep(wait)
                attempt += 1
                continue
            response = self._policy.check_response(method, url, response)
            wait = self._policy.status_retry_wait(method, url, response, attempt, deadline)
            if wait is None:
                return response
            await self._sleep(wait)
            attempt += 1
