import logging

import pytest

from aura_python_sdk import AuraConnectionError, AuraResponseError, AuraTimeoutError, HttpResponse
from aura_python_sdk._internal.http._service import HttpService
from tests.fakes import FakeClock, FakeTransport

URL = "https://api.neo4j.io/v1/instances"


def _service(
    transport: FakeTransport, clock: FakeClock, *, max_retries: int = 3, max_size: int = 1024
) -> HttpService:
    return HttpService(
        transport,
        max_retries=max_retries,
        max_response_size=max_size,
        logger=logging.getLogger("test"),
        clock=clock,
        sleep=clock.sleep,
    )


def _not_sent() -> AuraConnectionError:
    return AuraConnectionError("connect failed", request_sent=False)


def _sent() -> AuraConnectionError:
    return AuraConnectionError("connection reset", request_sent=True)


def test_passes_request_through() -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(200, body=b"ok")])
    response = _service(transport, clock).send(
        "POST", URL, {"X": "1"}, b"{}", deadline=clock.now + 30
    )

    assert response.body == b"ok"
    [request] = transport.requests
    assert (request.method, request.url, request.body) == ("POST", URL, b"{}")
    assert request.headers == {"X": "1"}
    assert request.timeout == 30
    assert request.max_response_size == 1024


@pytest.mark.parametrize("status", [429, 502, 503, 504])
@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_retryable_statuses_are_retried_for_idempotent_methods(status: int, method: str) -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(status), HttpResponse(status), HttpResponse(200)])
    response = _service(transport, clock).send(method, URL, {}, None, deadline=clock.now + 30)
    assert response.status_code == 200
    assert len(transport.requests) == 3
    assert clock.sleeps == [1.0, 2.0]


@pytest.mark.parametrize("status", [429, 502, 503, 504])
@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_retryable_statuses_are_not_retried_for_other_methods(status: int, method: str) -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(status)])
    response = _service(transport, clock).send(method, URL, {}, b"{}", deadline=clock.now + 30)
    assert response.status_code == status
    assert len(transport.requests) == 1


@pytest.mark.parametrize("status", [400, 401, 404, 409, 500])
def test_other_statuses_are_never_retried(status: int) -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(status)])
    response = _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 30)
    assert response.status_code == status
    assert len(transport.requests) == 1


def test_retry_after_is_honoured() -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(429, {"Retry-After": "7"}), HttpResponse(200)])
    _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 30)
    assert clock.sleeps == [7.0]


def test_retry_after_past_the_deadline_returns_the_response() -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(429, {"Retry-After": "60"})])
    response = _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 30)
    assert response.status_code == 429
    assert clock.sleeps == []


def test_status_and_network_retries_share_max_retries() -> None:
    clock = FakeClock()
    transport = FakeTransport([_sent(), HttpResponse(503), HttpResponse(503)])
    response = _service(transport, clock, max_retries=2).send(
        "GET", URL, {}, None, deadline=clock.now + 60
    )
    assert response.status_code == 503
    assert len(transport.requests) == 3


def test_retries_network_errors_with_backoff() -> None:
    clock = FakeClock()
    transport = FakeTransport([_sent(), _sent(), _sent(), HttpResponse(200)])
    response = _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 60)

    assert response.status_code == 200
    assert len(transport.requests) == 4
    assert clock.sleeps == [1.0, 2.0, 4.0]


def test_backoff_is_capped_at_five_seconds() -> None:
    clock = FakeClock()
    transport = FakeTransport([_not_sent()] * 5 + [HttpResponse(200)])
    _service(transport, clock, max_retries=5).send("GET", URL, {}, None, deadline=clock.now + 60)
    assert clock.sleeps == [1.0, 2.0, 4.0, 5.0, 5.0]


def test_gives_up_after_max_retries() -> None:
    clock = FakeClock()
    transport = FakeTransport([_not_sent()] * 3)
    with pytest.raises(AuraConnectionError):
        _service(transport, clock, max_retries=2).send(
            "GET", URL, {}, None, deadline=clock.now + 60
        )
    assert len(transport.requests) == 3


def test_zero_retries_means_single_attempt() -> None:
    clock = FakeClock()
    transport = FakeTransport([_not_sent()])
    with pytest.raises(AuraConnectionError):
        _service(transport, clock, max_retries=0).send(
            "GET", URL, {}, None, deadline=clock.now + 60
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_non_idempotent_request_not_retried_once_it_may_have_been_sent(method: str) -> None:
    clock = FakeClock()
    transport = FakeTransport([_sent()])
    with pytest.raises(AuraConnectionError):
        _service(transport, clock).send(method, URL, {}, b"{}", deadline=clock.now + 60)
    assert len(transport.requests) == 1


def test_non_idempotent_request_retried_when_never_sent() -> None:
    clock = FakeClock()
    transport = FakeTransport([_not_sent(), HttpResponse(202)])
    response = _service(transport, clock).send("POST", URL, {}, b"{}", deadline=clock.now + 60)
    assert response.status_code == 202
    assert len(transport.requests) == 2


def test_timeouts_are_retried_for_idempotent_methods() -> None:
    clock = FakeClock()
    transport = FakeTransport(
        [AuraTimeoutError("read timeout", request_sent=True), HttpResponse(200)]
    )
    _service(transport, clock).send("DELETE", URL, {}, None, deadline=clock.now + 60)
    assert len(transport.requests) == 2


def test_no_retry_when_backoff_would_pass_deadline() -> None:
    clock = FakeClock()
    transport = FakeTransport([_not_sent(), HttpResponse(200)])
    with pytest.raises(AuraConnectionError):
        _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 0.5)
    assert len(transport.requests) == 1


def test_each_attempt_gets_the_remaining_time() -> None:
    clock = FakeClock()
    transport = FakeTransport([_not_sent(), HttpResponse(200)])
    _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now + 10)
    assert [r.timeout for r in transport.requests] == [10.0, 9.0]


def test_expired_deadline_raises_timeout_without_sending() -> None:
    clock = FakeClock()
    transport = FakeTransport()
    with pytest.raises(AuraTimeoutError):
        _service(transport, clock).send("GET", URL, {}, None, deadline=clock.now)
    assert transport.requests == []


def test_oversized_body_rejected_even_if_transport_ignores_limit() -> None:
    clock = FakeClock()
    transport = FakeTransport([HttpResponse(200, body=b"x" * 11)])
    with pytest.raises(AuraResponseError, match="exceeded limit"):
        _service(transport, clock, max_size=10).send("GET", URL, {}, None, deadline=clock.now + 5)
