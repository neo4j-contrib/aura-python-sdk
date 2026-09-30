"""Authenticated Aura API requests (Go: internal/api RequestService)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from aura_python_sdk._errors import (
    AuraClientClosedError,
    AuraResponseError,
    api_error_from_response,
)
from aura_python_sdk._internal._auth import AsyncTokenManager, TokenManager
from aura_python_sdk._internal.http._service import AsyncHttpService, HttpService
from aura_python_sdk._transport import HttpResponse

QueryParams = Mapping[str, str | None]


def build_path(*segments: str) -> str:
    """Join path segments, percent-encoding each so an ID can never alter the path."""
    return "/".join(quote(segment, safe="") for segment in segments)


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> object:
        try:
            return json.loads(self.body)
        except ValueError as exc:
            raise AuraResponseError("response body is not valid JSON") from exc


class _Requests:
    """URL, header and body handling plus error mapping, shared by the sync and async services.

    A relative path such as ``instances/abc`` resolves to
    ``{base_url}/{api_version}/instances/abc``.
    An absolute ``http(s)://`` URL, such as a Prometheus metrics endpoint, is used unchanged but
    still gets the Aura bearer token.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_version: str,
        user_agent: str,
        default_headers: Mapping[str, str],
        timeout: float,
        logger: logging.Logger,
        is_closed: Callable[[], bool],
    ) -> None:
        self.endpoint_base = f"{base_url}/{api_version}"
        self.user_agent = user_agent
        self.default_headers = dict(default_headers)
        self.timeout = timeout
        self.logger = logger
        self.is_closed = is_closed

    def check_open(self) -> None:
        if self.is_closed():
            raise AuraClientClosedError("the client is closed; create a new client")

    def resolve_url(self, path: str, params: QueryParams | None) -> str:
        if path.startswith(("https://", "http://")):
            url = path
        else:
            url = f"{self.endpoint_base}/{path.lstrip('/')}"
        query = {key: value for key, value in (params or {}).items() if value is not None}
        if query:
            url += ("&" if "?" in url else "?") + urlencode(query)
        return url

    def headers(self, authorization: str) -> dict[str, str]:
        headers = dict(self.default_headers)
        headers["Content-Type"] = "application/json"
        headers["User-Agent"] = self.user_agent
        headers["Authorization"] = authorization
        return headers

    @staticmethod
    def body(json_body: object) -> bytes | None:
        return None if json_body is None else json.dumps(json_body, separators=(",", ":")).encode()

    def finish(
        self, method: str, url: str, response: HttpResponse, invalidate: Callable[[], None]
    ) -> ApiResponse:
        if not 200 <= response.status_code < 300:
            if response.status_code == 401:
                # The token may have been revoked; make the next call fetch a fresh one.
                invalidate()
            error = api_error_from_response(response.status_code, response.body, response.headers)
            self.logger.debug(
                "API returned error",
                extra={"method": method, "url": url, "status": response.status_code},
            )
            raise error
        return ApiResponse(response.status_code, response.headers, response.body)


class RequestService:
    """Adds authentication, headers and URL handling, and maps error responses to exceptions."""

    def __init__(
        self,
        *,
        http: HttpService,
        auth: TokenManager,
        base_url: str,
        api_version: str,
        user_agent: str,
        default_headers: Mapping[str, str],
        timeout: float,
        logger: logging.Logger,
        is_closed: Callable[[], bool] = lambda: False,
    ) -> None:
        self._http = http
        self._auth = auth
        self._requests = _Requests(
            base_url=base_url,
            api_version=api_version,
            user_agent=user_agent,
            default_headers=default_headers,
            timeout=timeout,
            logger=logger,
            is_closed=is_closed,
        )

    def get(self, path: str, *, params: QueryParams | None = None) -> ApiResponse:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, json_body: object = None) -> ApiResponse:
        return self.request("POST", path, json_body=json_body)

    def patch(self, path: str, *, json_body: object = None) -> ApiResponse:
        return self.request("PATCH", path, json_body=json_body)

    def put(self, path: str, *, json_body: object = None) -> ApiResponse:
        return self.request("PUT", path, json_body=json_body)

    def delete(self, path: str) -> ApiResponse:
        return self.request("DELETE", path)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: QueryParams | None = None,
        json_body: object = None,
    ) -> ApiResponse:
        self._requests.check_open()
        # One deadline covers the token fetch, every attempt and every backoff, like the
        # context.WithTimeout that wraps each Go service method.
        deadline = self._http.clock() + self._requests.timeout
        url = self._requests.resolve_url(path, params)
        headers = self._requests.headers(self._auth.authorization_header(deadline=deadline))
        self._requests.logger.debug(
            "making authenticated API request", extra={"method": method, "url": url}
        )
        response = self._http.send(
            method, url, headers, self._requests.body(json_body), deadline=deadline
        )
        return self._requests.finish(method, url, response, self._auth.invalidate)


class AsyncRequestService:
    """The asyncio version of :class:`RequestService`."""

    def __init__(
        self,
        *,
        http: AsyncHttpService,
        auth: AsyncTokenManager,
        base_url: str,
        api_version: str,
        user_agent: str,
        default_headers: Mapping[str, str],
        timeout: float,
        logger: logging.Logger,
        is_closed: Callable[[], bool] = lambda: False,
    ) -> None:
        self._http = http
        self._auth = auth
        self._requests = _Requests(
            base_url=base_url,
            api_version=api_version,
            user_agent=user_agent,
            default_headers=default_headers,
            timeout=timeout,
            logger=logger,
            is_closed=is_closed,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: QueryParams | None = None,
        json_body: object = None,
    ) -> ApiResponse:
        self._requests.check_open()
        deadline = self._http.clock() + self._requests.timeout
        url = self._requests.resolve_url(path, params)
        authorization = await self._auth.authorization_header(deadline=deadline)
        headers = self._requests.headers(authorization)
        self._requests.logger.debug(
            "making authenticated API request", extra={"method": method, "url": url}
        )
        response = await self._http.send(
            method, url, headers, self._requests.body(json_body), deadline=deadline
        )
        return self._requests.finish(method, url, response, self._auth.invalidate)
