import json
import logging

import pytest

from aura_python_sdk import AuraResponseError, AuthenticationError, HttpResponse, NotFoundError
from aura_python_sdk._internal._auth import TokenManager
from aura_python_sdk._internal._request import RequestService, build_path
from aura_python_sdk._internal.http._service import HttpService
from tests.fakes import FakeClock, FakeTransport, json_response, token_response

BASE = "https://api.neo4j.io"


def _service(
    transport: FakeTransport,
    *,
    timeout: float = 30.0,
    default_headers: dict[str, str] | None = None,
) -> RequestService:
    clock = FakeClock()
    logger = logging.getLogger("test")
    http = HttpService(
        transport,
        max_retries=0,
        max_response_size=1 << 20,
        logger=logger,
        clock=clock,
        sleep=clock.sleep,
    )
    auth = TokenManager(
        client_id="id",
        client_secret="secret",
        token_url=f"{BASE}/oauth/token",
        user_agent="ua/1",
        http=http,
        logger=logger,
    )
    return RequestService(
        http=http,
        auth=auth,
        base_url=BASE,
        api_version="v1",
        user_agent="ua/1",
        default_headers=default_headers or {},
        timeout=timeout,
        logger=logger,
    )


def test_relative_path_gets_versioned_base_url() -> None:
    transport = FakeTransport([token_response(), json_response(200, {"data": []})])
    _service(transport).get("instances")
    assert transport.api_requests[0].url == f"{BASE}/v1/instances"


def test_leading_slash_is_tolerated() -> None:
    transport = FakeTransport([token_response(), json_response(200, {})])
    _service(transport).get("/tenants")
    assert transport.api_requests[0].url == f"{BASE}/v1/tenants"


def test_absolute_url_passes_through_with_auth() -> None:
    prometheus = "https://abc.metrics.neo4j.io/prometheus/metrics"
    transport = FakeTransport([token_response("tok"), HttpResponse(200, body=b"metric 1")])
    response = _service(transport).get(prometheus)

    [request] = transport.api_requests
    assert request.url == prometheus
    assert request.headers["Authorization"] == "Bearer tok"
    assert response.body == b"metric 1"


def test_query_params_encoded_and_none_dropped() -> None:
    transport = FakeTransport([token_response(), json_response(200, {}), json_response(200, {})])
    service = _service(transport)
    service.get("customer-managed-keys", params={"tenantId": "a b&c", "other": None})
    service.get("x?y=1", params={"z": "2"})
    urls = [r.url for r in transport.api_requests]
    assert urls == [f"{BASE}/v1/customer-managed-keys?tenantId=a+b%26c", f"{BASE}/v1/x?y=1&z=2"]


def test_headers() -> None:
    transport = FakeTransport([token_response("tok"), json_response(200, {})])
    _service(transport, default_headers={"X-Trace": "t1"}).get("instances")
    headers = transport.api_requests[0].headers
    assert headers == {
        "X-Trace": "t1",
        "Content-Type": "application/json",
        "User-Agent": "ua/1",
        "Authorization": "Bearer tok",
    }


def test_json_body_is_serialised() -> None:
    transport = FakeTransport([token_response(), json_response(202, {"data": {}})])
    response = _service(transport).post("instances", json_body={"name": "Instance01", "n": 1})
    request = transport.api_requests[0]
    assert request.method == "POST"
    assert request.body is not None
    assert json.loads(request.body) == {"name": "Instance01", "n": 1}
    assert response.status_code == 202


def test_no_body_when_json_body_is_none() -> None:
    transport = FakeTransport([token_response(), json_response(202, {})])
    _service(transport).post("instances/abcd1234/pause")
    assert transport.api_requests[0].body is None


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("GET", lambda s: s.get("p")),
        ("POST", lambda s: s.post("p")),
        ("PATCH", lambda s: s.patch("p", json_body={})),
        ("PUT", lambda s: s.put("p", json_body={})),
        ("DELETE", lambda s: s.delete("p")),
    ],
)
def test_verbs(method: str, call: object) -> None:
    transport = FakeTransport([token_response(), json_response(200, {})])
    call(_service(transport))  # type: ignore[operator]
    assert transport.api_requests[0].method == method


def test_error_response_raises_mapped_exception() -> None:
    body = {"errors": [{"message": "Instance not found", "reason": "instance-not-found"}]}
    transport = FakeTransport([token_response(), json_response(404, body, {"X-Request-Id": "r1"})])
    with pytest.raises(NotFoundError) as info:
        _service(transport).get("instances/abcd1234")
    assert info.value.request_id == "r1"
    assert info.value.details[0].message == "Instance not found"


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_401_retries_once_with_a_fresh_token(method: str) -> None:
    # The server rejects a request with a revoked token before acting on it, so even a POST
    # is safe to resend.
    transport = FakeTransport(
        [
            token_response("old"),
            json_response(401, {"errors": [{"message": "expired"}]}),
            token_response("new"),
            json_response(200, {}),
        ]
    )
    _service(transport).request(method, "instances", json_body={"a": 1})
    assert [r.headers["Authorization"] for r in transport.api_requests] == [
        "Bearer old",
        "Bearer new",
    ]
    assert [r.body for r in transport.api_requests] == [b'{"a":1}', b'{"a":1}']


def test_second_401_raises_and_drops_the_token() -> None:
    transport = FakeTransport(
        [
            token_response("old"),
            json_response(401, {"errors": [{"message": "expired"}]}),
            token_response("new"),
            json_response(401, {"errors": [{"message": "no access"}]}),
            token_response("newer"),
            json_response(200, {}),
        ]
    )
    service = _service(transport)
    with pytest.raises(AuthenticationError, match="no access"):
        service.get("instances")
    service.get("instances")
    assert [r.headers["Authorization"] for r in transport.api_requests] == [
        "Bearer old",
        "Bearer new",
        "Bearer newer",
    ]


def test_token_fetch_shares_the_call_deadline() -> None:
    transport = FakeTransport([token_response(), json_response(200, {})])
    _service(transport, timeout=12.0).get("instances")
    assert [r.timeout for r in transport.requests] == [12.0, 12.0]


def test_response_json() -> None:
    transport = FakeTransport([token_response(), json_response(200, {"data": [1]})])
    assert _service(transport).get("x").json() == {"data": [1]}


def test_response_json_invalid() -> None:
    transport = FakeTransport([token_response(), HttpResponse(200, body=b"<html>")])
    with pytest.raises(AuraResponseError, match="not valid JSON"):
        _service(transport).get("x").json()


def test_build_path_encodes_segments() -> None:
    assert build_path("instances", "abcd1234", "snapshots") == "instances/abcd1234/snapshots"
    assert build_path("sessions", "../x?y") == "sessions/..%2Fx%3Fy"
