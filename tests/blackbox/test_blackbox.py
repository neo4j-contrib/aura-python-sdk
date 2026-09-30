"""End-to-end over real sockets and the real httpx transport (Go: client_blackbox_test.go)."""

import base64
import socket
import time

import pytest

import aura_python_sdk as aura
from tests.blackbox.conftest import FakeAura, Received, Reply

TENANT_ID = "6981ace7-efe8-4f5c-b7c5-267b5162ce91"
INSTANCE = {
    "id": "2f49c2b3",
    "name": "Production",
    "status": "running",
    "tenant_id": TENANT_ID,
    "cloud_provider": "gcp",
    "connection_url": "neo4j+s://2f49c2b3.databases.neo4j.io",
    "region": "europe-west1",
    "type": "enterprise-db",
    "memory": "8GB",
}


def test_list_instances_end_to_end(fake_aura: FakeAura) -> None:
    fake_aura.route(
        "GET",
        "/v1/instances",
        Reply.json(
            200,
            {
                "data": [
                    {"id": "2f49c2b3", "name": "P", "tenant_id": TENANT_ID, "cloud_provider": "gcp"}
                ]
            },
        ),
    )
    with fake_aura.client(default_headers={"X-Team": "db"}) as client:
        [instance] = client.instances.list(tenant_id=TENANT_ID)

    assert instance.id == "2f49c2b3"
    token_request, api_request = fake_aura.received
    assert (
        token_request.headers["authorization"]
        == "Basic " + base64.b64encode(b"local-id:local-secret").decode()
    )
    assert token_request.body == b"grant_type=client_credentials"
    assert api_request.query == f"tenantId={TENANT_ID}"
    assert api_request.headers["authorization"] == "Bearer local-token"
    assert api_request.headers["user-agent"] == f"aura-python-sdk/{aura.__version__}"
    assert api_request.headers["content-type"] == "application/json"
    assert api_request.headers["x-team"] == "db"


def test_token_is_reused_across_calls(fake_aura: FakeAura) -> None:
    fake_aura.route("GET", "/v1/instances/2f49c2b3", Reply.json(200, {"data": INSTANCE}))
    with fake_aura.client() as client:
        for _ in range(3):
            client.instances.get("2f49c2b3")
    assert [r.path for r in fake_aura.received].count("/oauth/token") == 1


def test_create_sends_json_body(fake_aura: FakeAura) -> None:
    created = {
        **INSTANCE,
        "id": "db1d1234",
        "username": "neo4j",
        "password": "secret-pw",
    }
    fake_aura.route("POST", "/v1/instances", Reply.json(202, {"data": created}))
    config = aura.InstanceConfig(
        name="Instance01",
        tenant_id=TENANT_ID,
        cloud_provider=aura.CloudProvider.GCP,
        region="europe-west1",
        type=aura.InstanceType.ENTERPRISE_DB,
        version="5",
        memory="8GB",
    )
    with fake_aura.client() as client:
        result = client.instances.create(config)
    assert result.password == "secret-pw"
    assert fake_aura.api_requests()[0].json()["type"] == "enterprise-db"


def test_api_error_is_mapped(fake_aura: FakeAura) -> None:
    fake_aura.route(
        "GET",
        "/v1/instances/2f49c2b3",
        Reply.json(
            404,
            {"errors": [{"message": "Instance not found", "reason": "instance-not-found"}]},
            **{"X-Request-Id": "req-42"},
        ),
    )
    with fake_aura.client() as client, pytest.raises(aura.NotFoundError) as info:
        client.instances.get("2f49c2b3")
    assert info.value.request_id == "req-42"
    assert info.value.details[0].reason == "instance-not-found"


def test_rejected_credentials(fake_aura: FakeAura) -> None:
    fake_aura.route("POST", "/oauth/token", Reply.json(401, {"error": "access_denied"}))
    with (
        fake_aura.client() as client,
        pytest.raises(aura.AuthenticationError, match="access_denied"),
    ):
        client.tenants.list()
    assert fake_aura.api_requests() == []


def test_rate_limit_past_the_deadline_is_raised(fake_aura: FakeAura) -> None:
    # Retry-After (7 s) is longer than the 5 s timeout, so the client doesn't wait.
    fake_aura.route(
        "GET",
        "/v1/tenants",
        Reply.json(429, {"error": "Rate limit exceeded"}, **{"Retry-After": "7"}),
    )
    with fake_aura.client() as client, pytest.raises(aura.RateLimitError) as info:
        client.tenants.list()
    assert info.value.retry_after == 7.0
    assert len(fake_aura.api_requests()) == 1


def test_service_unavailable_is_retried_for_get(fake_aura: FakeAura) -> None:
    replies = iter(
        [
            Reply.json(503, {"error": "unavailable"}, **{"Retry-After": "0"}),
            Reply.json(200, {"data": []}),
        ]
    )
    fake_aura.route("GET", "/v1/tenants", lambda _: next(replies))
    with fake_aura.client() as client:
        assert client.tenants.list() == []
    assert len(fake_aura.api_requests()) == 2


def test_service_unavailable_is_not_retried_for_post(fake_aura: FakeAura) -> None:
    fake_aura.route("POST", "/v1/instances/abcd1234/pause", Reply.json(503, {"error": "busy"}))
    with fake_aura.client() as client, pytest.raises(aura.ServerError):
        client.instances.pause("abcd1234")
    assert len(fake_aura.api_requests()) == 1


def test_permanent_redirect_is_followed(fake_aura: FakeAura) -> None:
    fake_aura.route(
        "GET", "/v1/tenants", Reply(308, headers={"Location": f"{fake_aura.url}/v1/tenants-moved"})
    )
    fake_aura.route("GET", "/v1/tenants-moved", Reply.json(200, {"data": []}))
    with fake_aura.client() as client:
        assert client.tenants.list() == []


def test_response_size_limit(fake_aura: FakeAura) -> None:
    fake_aura.route("GET", "/v1/tenants", Reply.json(200, {"data": [], "padding": "x" * 5000}))
    with (
        fake_aura.client(max_response_size=1024) as client,
        pytest.raises(aura.AuraResponseError, match="exceeded limit"),
    ):
        client.tenants.list()


def test_delete_with_no_content(fake_aura: FakeAura) -> None:
    fake_aura.route("DELETE", "/v1/customer-managed-keys/key-1", Reply(204))
    with fake_aura.client() as client:
        client.cmek.delete("key-1")
    assert fake_aura.api_requests()[0].method == "DELETE"


def test_slow_post_times_out_and_is_not_retried(fake_aura: FakeAura) -> None:
    fake_aura.route("POST", "/v1/instances/2f49c2b3/pause", Reply(202, b"{}", delay=2.0))
    started = time.monotonic()
    with (
        fake_aura.client(timeout=0.5, max_retries=3) as client,
        pytest.raises(aura.AuraTimeoutError),
    ):
        client.instances.pause("2f49c2b3")
    assert time.monotonic() - started < 1.9
    assert len(fake_aura.api_requests()) == 1


def test_connection_refused(fake_aura: FakeAura) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    client = aura.AuraClient(
        client_id="id",
        client_secret="secret",
        base_url=f"http://127.0.0.1:{closed_port}",
        allow_insecure_base_url=True,
        max_retries=0,
        timeout=5,
    )
    with client, pytest.raises(aura.AuraConnectionError) as info:
        client.tenants.list()
    assert info.value.request_sent is False


def test_prometheus_over_http(fake_aura: FakeAura) -> None:
    text = b"# TYPE neo4j_aura_cpu_usage gauge\nneo4j_aura_cpu_usage 0.5\n"
    fake_aura.route("GET", "/metrics", Reply(200, text, {"Content-Type": "text/plain"}))
    with fake_aura.client(allow_untrusted_metrics_urls=True) as client:
        metrics = client.prometheus.fetch_raw_metrics(f"{fake_aura.url}/metrics")
        assert client.prometheus.get_metric_value(metrics, "neo4j_aura_cpu_usage") == 0.5
    assert fake_aura.api_requests()[0].headers["authorization"] == "Bearer local-token"


def test_dynamic_route(fake_aura: FakeAura) -> None:
    def echo_patch(request: Received) -> Reply:
        return Reply.json(200, {"data": {**INSTANCE, **request.json()}})

    fake_aura.route("PATCH", "/v1/instances/2f49c2b3", echo_patch)
    with fake_aura.client() as client:
        assert client.instances.update("2f49c2b3", name="Renamed").name == "Renamed"
