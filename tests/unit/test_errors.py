import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from aura_python_sdk import (
    AuraAPIError,
    AuraError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ErrorDetail,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)
from aura_python_sdk._errors import api_error_from_response


def _body(payload: object) -> bytes:
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (405, AuraAPIError),
        (415, AuraAPIError),
        (420, AuraAPIError),
    ],
)
def test_status_maps_to_error_class(status: int, expected: type[AuraAPIError]) -> None:
    error = api_error_from_response(status, b"", {})
    assert type(error) is expected
    assert isinstance(error, AuraError)
    assert error.status_code == status


def test_spec_errors_shape() -> None:
    body = _body(
        {
            "errors": [
                {"message": "Instance not found", "reason": "instance-not-found"},
                {"message": "second", "reason": "other", "field": "name"},
            ]
        }
    )
    error = api_error_from_response(404, body, {"x-request-id": "req-123"})

    assert error.message == "Not Found"
    assert error.details == (
        ErrorDetail("Instance not found", "instance-not-found"),
        ErrorDetail("second", "other", "name"),
    )
    assert error.request_id == "req-123"
    assert error.is_not_found
    assert error.has_multiple_errors
    assert error.all_errors() == ["Not Found", "Instance not found", "second"]
    # Same format as the Go SDK's Error() string.
    assert (
        str(error) == "API error (status 404): Not Found - Instance not found (and 1 more error(s))"
    )


def test_single_detail_message_format() -> None:
    error = api_error_from_response(400, _body({"errors": [{"message": "bad name"}]}), {})
    assert str(error) == "API error (status 400): Bad Request - bad name"
    assert error.is_bad_request
    assert not error.has_multiple_errors


def test_message_and_details_keys() -> None:
    body = _body({"message": "Validation failed", "details": [{"message": "memory invalid"}]})
    error = api_error_from_response(400, body, {})
    assert error.message == "Validation failed"
    assert [d.message for d in error.details] == ["memory invalid"]


def test_middleware_error_shape() -> None:
    error = api_error_from_response(429, _body({"error": "Rate limit exceeded"}), {})
    assert error.message == "Rate limit exceeded"
    assert str(error) == "API error (status 429): Rate limit exceeded"


@pytest.mark.parametrize("body", [b"", b"not json", b"[1, 2]", b'"text"', _body({"errors": "x"})])
def test_unparseable_bodies_fall_back_to_status_phrase(body: bytes) -> None:
    error = api_error_from_response(502, body, {})
    assert error.message == "Bad Gateway"
    assert error.details == ()


def test_unknown_status_code_phrase() -> None:
    assert api_error_from_response(420, b"", {}).message == "HTTP 420"


def test_retry_after_seconds() -> None:
    error = api_error_from_response(429, b"", {"retry-after": "30"})
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 30.0


def test_retry_after_http_date() -> None:
    when = datetime.now(UTC) + timedelta(seconds=120)
    error = api_error_from_response(429, b"", {"retry-after": format_datetime(when, usegmt=True)})
    assert isinstance(error, RateLimitError)
    assert error.retry_after is not None
    assert 100 < error.retry_after <= 120


@pytest.mark.parametrize("value", [None, "", "soon"])
def test_retry_after_missing_or_invalid(value: str | None) -> None:
    headers = {} if value is None else {"retry-after": value}
    error = api_error_from_response(429, b"", headers)
    assert isinstance(error, RateLimitError)
    assert error.retry_after is None


def test_error_class_override_keeps_details() -> None:
    error = api_error_from_response(
        400, _body({"errors": [{"message": "invalid_client"}]}), {}, error_class=AuthenticationError
    )
    assert type(error) is AuthenticationError
    assert error.status_code == 400
    assert error.details[0].message == "invalid_client"


def test_is_unauthorized() -> None:
    assert api_error_from_response(401, b"", {}).is_unauthorized
    assert not api_error_from_response(403, b"", {}).is_unauthorized
