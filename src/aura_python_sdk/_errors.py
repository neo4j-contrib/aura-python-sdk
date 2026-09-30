"""Exceptions raised by the SDK.

Every exception derives from :class:`AuraError`. Errors returned by the Aura API are
:class:`AuraAPIError` subclasses chosen by HTTP status, so callers can write
``except NotFoundError:`` where the Go SDK uses ``aura.IsNotFound(err)``.
"""

from __future__ import annotations

import email.utils
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus


class AuraError(Exception):
    """Base class for all errors raised by this SDK."""


class AuraConfigurationError(AuraError, ValueError):
    """The client was constructed with invalid options."""


class AuraValidationError(AuraError, ValueError):
    """An argument failed client-side validation; no request was sent."""


class AuraConnectionError(AuraError):
    """The request could not be completed because of a network failure.

    ``request_sent`` is False when the failure happened before the request reached the server
    (for example DNS or connect errors), so retrying cannot duplicate the operation.
    """

    def __init__(self, message: str, *, request_sent: bool) -> None:
        super().__init__(message)
        self.request_sent = request_sent


class AuraTimeoutError(AuraConnectionError):
    """The request did not complete within the configured timeout."""


class AuraResponseError(AuraError):
    """The API response could not be used: too large, not valid JSON, or an unexpected shape."""


class MetricNotFoundError(AuraError, LookupError):
    """No Prometheus metric matched the requested name and label filters."""


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    """One entry from the ``errors`` array of an Aura API error response."""

    message: str
    reason: str | None = None
    field: str | None = None


class AuraAPIError(AuraError):
    """The Aura API returned a non-2xx response."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: Sequence[ErrorDetail] = (),
        *,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.details: tuple[ErrorDetail, ...] = tuple(details)
        self.request_id = request_id
        super().__init__(self._format())

    def _format(self) -> str:
        text = f"API error (status {self.status_code}): {self.message}"
        if self.details:
            text += f" - {self.details[0].message}"
            if len(self.details) > 1:
                text += f" (and {len(self.details) - 1} more error(s))"
        return text

    def all_errors(self) -> list[str]:
        """The top-level message followed by every detail message."""
        return [self.message, *(detail.message for detail in self.details)]

    @property
    def has_multiple_errors(self) -> bool:
        return len(self.details) > 1

    @property
    def is_not_found(self) -> bool:
        return self.status_code == HTTPStatus.NOT_FOUND

    @property
    def is_unauthorized(self) -> bool:
        return self.status_code == HTTPStatus.UNAUTHORIZED

    @property
    def is_bad_request(self) -> bool:
        return self.status_code == HTTPStatus.BAD_REQUEST


class BadRequestError(AuraAPIError):
    """HTTP 400."""


class AuthenticationError(AuraAPIError):
    """HTTP 401, or the OAuth token request was rejected."""


class PermissionDeniedError(AuraAPIError):
    """HTTP 403."""


class NotFoundError(AuraAPIError):
    """HTTP 404."""


class ConflictError(AuraAPIError):
    """HTTP 409."""


class RateLimitError(AuraAPIError):
    """HTTP 429. ``retry_after`` is the server's suggested wait in seconds, if it sent one."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: Sequence[ErrorDetail] = (),
        *,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(status_code, message, details, request_id=request_id)


class ServerError(AuraAPIError):
    """HTTP 5xx."""


_STATUS_TO_ERROR: dict[int, type[AuraAPIError]] = {
    HTTPStatus.BAD_REQUEST: BadRequestError,
    HTTPStatus.UNAUTHORIZED: AuthenticationError,
    HTTPStatus.FORBIDDEN: PermissionDeniedError,
    HTTPStatus.NOT_FOUND: NotFoundError,
    HTTPStatus.CONFLICT: ConflictError,
}


def api_error_from_response(
    status_code: int,
    body: bytes,
    headers: Mapping[str, str],
    *,
    error_class: type[AuraAPIError] | None = None,
) -> AuraAPIError:
    """Build the exception for a non-2xx response.

    Understands the spec's ``{"errors": [...]}`` shape, the middleware ``{"error": "..."}`` shape,
    and ``message`` / ``details`` keys. ``headers`` must have lower-case keys.
    """
    message, details = _parse_error_body(body)
    if message is None:
        message = _status_phrase(status_code)
    request_id = headers.get("x-request-id")

    if status_code == HTTPStatus.TOO_MANY_REQUESTS:
        return RateLimitError(
            status_code,
            message,
            details,
            request_id=request_id,
            retry_after=_parse_retry_after(headers.get("retry-after")),
        )
    if error_class is None:
        error_class = _STATUS_TO_ERROR.get(status_code)
    if error_class is None:
        error_class = ServerError if status_code >= 500 else AuraAPIError
    return error_class(status_code, message, details, request_id=request_id)


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return f"HTTP {status_code}"


def _parse_error_body(body: bytes) -> tuple[str | None, list[ErrorDetail]]:
    if not body:
        return None, []
    try:
        payload = json.loads(body)
    except ValueError:
        return None, []
    if not isinstance(payload, dict):
        return None, []

    message = payload.get("message")
    if not isinstance(message, str) or not message:
        middleware_error = payload.get("error")
        message = (
            middleware_error if isinstance(middleware_error, str) and middleware_error else None
        )

    raw_details = payload.get("errors") or payload.get("details") or []
    details = (
        [
            ErrorDetail(
                message=str(item.get("message", "")),
                reason=_optional_str(item.get("reason")),
                field=_optional_str(item.get("field")),
            )
            for item in raw_details
            if isinstance(item, dict)
        ]
        if isinstance(raw_details, list)
        else []
    )
    return message, details


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either delta-seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, parsed.timestamp() - time.time())


# Report the public import path in tracebacks and reprs: "aura_python_sdk.NotFoundError", not
# "aura_python_sdk._errors.NotFoundError". Every class listed here is exported from the package.
for _public in (
    AuraError,
    AuraConfigurationError,
    AuraValidationError,
    AuraConnectionError,
    AuraTimeoutError,
    AuraResponseError,
    MetricNotFoundError,
    ErrorDetail,
    AuraAPIError,
    BadRequestError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    ServerError,
):
    _public.__module__ = "aura_python_sdk"
del _public
