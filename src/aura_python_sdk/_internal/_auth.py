"""OAuth client-credentials token management (Go: internal/api authManager).

``_TokenSource`` holds everything except I/O and locking: the token request, response
validation, and freshness checks. ``TokenManager`` (threads) and ``AsyncTokenManager`` (asyncio)
add only a lock and the send.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

from aura_python_sdk._errors import AuraResponseError, AuthenticationError, api_error_from_response
from aura_python_sdk._internal.http._service import AsyncHttpService, HttpService
from aura_python_sdk._transport import HttpResponse

# Refresh this many seconds before the token actually expires.
REFRESH_MARGIN = 60.0
MAX_EXPIRES_IN = 86400 * 365


@dataclass(frozen=True, slots=True)
class _Token:
    token_type: str
    # Kept out of repr: crash reporters record the repr of local variables.
    access_token: str = field(repr=False)
    expires_at: float  # on the HttpService clock (monotonic)

    @property
    def header(self) -> str:
        return f"{self.token_type} {self.access_token}"


class _TokenSource:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_url: str,
        user_agent: str,
        clock: Callable[[], float],
        logger: logging.Logger,
    ) -> None:
        credentials = f"{client_id}:{client_secret}".encode()
        self.url = token_url
        self.headers = {
            "Authorization": "Basic " + base64.b64encode(credentials).decode("ascii"),
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": user_agent,
        }
        self.body = urlencode({"grant_type": "client_credentials"}).encode("ascii")
        self.clock = clock
        self.logger = logger
        self.token: _Token | None = None

    def cached(self) -> _Token | None:
        token = self.token
        if token is not None and self.clock() < token.expires_at - REFRESH_MARGIN:
            return token
        return None

    def accept(self, response: HttpResponse) -> _Token:
        """Validate a token response, cache the token, and return it."""
        if not 200 <= response.status_code < 300:
            status = response.status_code
            # Any client error from the token endpoint means the credentials were rejected.
            # Rate limits and server errors keep their usual types.
            error_class = None if status == 429 or status >= 500 else AuthenticationError
            self.logger.debug("token request failed", extra={"status": status})
            raise api_error_from_response(
                status, response.body, response.headers, error_class=error_class
            )

        try:
            payload = json.loads(response.body)
            token_type = payload["token_type"]
            access_token = payload["access_token"]
            expires_in = payload["expires_in"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AuraResponseError("failed to parse token response") from exc

        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise AuraResponseError(f"token type is not valid: {token_type!r}")
        if not isinstance(access_token, str) or not access_token:
            raise AuraResponseError("token response did not contain an access token")
        if (
            isinstance(expires_in, bool)
            or not isinstance(expires_in, int | float)
            or not 0 < expires_in <= MAX_EXPIRES_IN
        ):
            raise AuraResponseError(f"invalid expires_in value: {expires_in!r}")

        self.logger.debug("token obtained", extra={"expires_in": expires_in})
        self.token = _Token(
            token_type="Bearer",  # noqa: S106 - the OAuth scheme name, not a secret
            access_token=access_token,
            expires_at=self.clock() + float(expires_in),
        )
        return self.token


class TokenManager:
    """Obtains and caches a bearer token from ``{base_url}/oauth/token``.

    Thread-safe. Concurrent callers that find the token missing or near expiry trigger a single
    refresh between them.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_url: str,
        user_agent: str,
        http: HttpService,
        logger: logging.Logger,
    ) -> None:
        self._source = _TokenSource(
            client_id=client_id,
            client_secret=client_secret,
            token_url=token_url,
            user_agent=user_agent,
            clock=http.clock,
            logger=logger,
        )
        self._http = http
        self._lock = threading.Lock()

    def authorization_header(self, *, deadline: float) -> str:
        """Return a valid ``Authorization`` header value, fetching a new token if needed."""
        token = self._source.cached()
        if token is None:
            with self._lock:
                # Another thread may have refreshed the token while this one waited.
                token = self._source.cached() or self._fetch(deadline)
        return token.header

    def _fetch(self, deadline: float) -> _Token:
        source = self._source
        source.logger.debug("obtaining new authentication token")
        response = self._http.send(
            "POST", source.url, source.headers, source.body, deadline=deadline
        )
        return source.accept(response)

    def invalidate(self) -> None:
        """Drop the cached token so the next request fetches a new one (e.g. after a 401)."""
        with self._lock:
            self._source.token = None


class AsyncTokenManager:
    """The asyncio version of :class:`TokenManager`. Concurrent tasks share one refresh."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_url: str,
        user_agent: str,
        http: AsyncHttpService,
        logger: logging.Logger,
    ) -> None:
        self._source = _TokenSource(
            client_id=client_id,
            client_secret=client_secret,
            token_url=token_url,
            user_agent=user_agent,
            clock=http.clock,
            logger=logger,
        )
        self._http = http
        self._lock = asyncio.Lock()

    async def authorization_header(self, *, deadline: float) -> str:
        token = self._source.cached()
        if token is None:
            async with self._lock:
                # Another task may have refreshed the token while this one waited.
                token = self._source.cached() or await self._fetch(deadline)
        return token.header

    async def _fetch(self, deadline: float) -> _Token:
        source = self._source
        source.logger.debug("obtaining new authentication token")
        response = await self._http.send(
            "POST", source.url, source.headers, source.body, deadline=deadline
        )
        return source.accept(response)

    def invalidate(self) -> None:
        # Safe without the lock: asyncio runs this between awaits, never mid-refresh.
        self._source.token = None
