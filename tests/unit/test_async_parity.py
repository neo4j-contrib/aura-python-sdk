"""The async client must behave exactly like the sync client.

Every public method of every service runs through both clients against the same canned
responses. The test asserts that the requests on the wire and the parsed results are identical,
and that the method signatures match. Adding a method without a case here fails the coverage
test.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import inspect
from collections.abc import Callable
from typing import Any

import pytest

import aura_python_sdk as aura
from aura_python_sdk import services
from aura_python_sdk._transport import HttpResponse
from tests.fakes import FakeAsyncTransport, FakeTransport, json_response, token_response
from tests.unit.conftest import (
    INSTANCE,
    INSTANCE_ID,
    OTHER_INSTANCE_ID,
    SESSION,
    SNAPSHOT_ID,
    TENANT_ID,
)

SERVICE_PAIRS = [
    (services.TenantService, services.AsyncTenantService),
    (services.InstanceService, services.AsyncInstanceService),
    (services.SnapshotService, services.AsyncSnapshotService),
    (services.CMEKService, services.AsyncCMEKService),
    (services.GDSSessionService, services.AsyncGDSSessionService),
    (services.PrometheusService, services.AsyncPrometheusService),
]

CONFIG = aura.InstanceConfig(
    name="Instance01",
    tenant_id=TENANT_ID,
    cloud_provider=aura.CloudProvider.GCP,
    region="europe-west1",
    type=aura.InstanceType.ENTERPRISE_DB,
    version="5",
    memory="8GB",
)
CREATED = {**INSTANCE, "username": "neo4j", "password": "pw"}
SNAPSHOT = {"instance_id": INSTANCE_ID, "snapshot_id": SNAPSHOT_ID, "status": "Completed"}
KEY = {
    "id": "8c764aed-8eb3-4a1c-92f6-e4ef0c7a6ed9",
    "name": "Key01",
    "tenant_id": TENANT_ID,
    "cloud_provider": "aws",
    "region": "us-west-2",
    "instance_type": "enterprise-db",
    "key_id": "arn:aws:kms:us-west-2:1:key/abc",
    "status": "pending",
}
METRICS_URL = "https://customer-metrics-api.neo4j.io/api/v1/p/2f49c2b3/metrics"
METRICS = HttpResponse(
    200,
    body=b"# TYPE neo4j_aura_cpu_usage gauge\nneo4j_aura_cpu_usage 3\n"
    b"# TYPE neo4j_aura_cpu_limit gauge\nneo4j_aura_cpu_limit 4\n",
)


def data(payload: object, status: int = 200) -> HttpResponse:
    return json_response(status, {"data": payload})


# (service, method, args, kwargs, replies)
CASES: list[tuple[str, str, tuple[Any, ...], dict[str, Any], list[HttpResponse]]] = [
    ("tenants", "list", (), {}, [data([{"id": TENANT_ID, "name": "t"}])]),
    ("tenants", "get", (TENANT_ID,), {}, [data({"id": TENANT_ID, "name": "t"})]),
    ("tenants", "get_metrics_integration", (TENANT_ID,), {}, [data({"endpoint": METRICS_URL})]),
    ("instances", "list", (TENANT_ID,), {}, [data([])]),
    ("instances", "get", (INSTANCE_ID,), {}, [data(INSTANCE)]),
    ("instances", "create", (CONFIG,), {}, [data(CREATED, 202)]),
    ("instances", "create_from_instance", (OTHER_INSTANCE_ID, CONFIG), {}, [data(CREATED, 202)]),
    (
        "instances",
        "create_from_snapshot",
        (OTHER_INSTANCE_ID, SNAPSHOT_ID, CONFIG),
        {},
        [data(CREATED, 202)],
    ),
    (
        "instances",
        "update",
        (INSTANCE_ID,),
        {"name": "Renamed", "storage": "32GB", "vector_optimized": True, "secondaries_count": 1},
        [data(INSTANCE, 202)],
    ),
    (
        "instances",
        "estimate_size",
        (),
        {"node_count": 10, "relationship_count": 20, "algorithm_categories": ["pathfinding"]},
        [
            data(
                {
                    "did_exceed_maximum": False,
                    "min_required_memory": "1GB",
                    "recommended_size": "2GB",
                }
            )
        ],
    ),
    (
        "instances",
        "upgrade",
        (INSTANCE_ID,),
        {"memory": "16GB", "storage": "32GB"},
        [data(INSTANCE)],
    ),
    ("instances", "delete", (INSTANCE_ID,), {}, [data(INSTANCE, 202)]),
    ("instances", "pause", (INSTANCE_ID,), {}, [data(INSTANCE, 202)]),
    ("instances", "resume", (INSTANCE_ID,), {}, [data(INSTANCE, 202)]),
    (
        "instances",
        "overwrite_from_instance",
        (INSTANCE_ID, OTHER_INSTANCE_ID),
        {},
        [data(INSTANCE, 202)],
    ),
    ("instances", "overwrite_from_snapshot", (INSTANCE_ID, SNAPSHOT_ID), {}, [data(INSTANCE, 202)]),
    ("snapshots", "list", (INSTANCE_ID, dt.date(2026, 1, 2)), {}, [data([SNAPSHOT])]),
    ("snapshots", "get", (INSTANCE_ID, SNAPSHOT_ID), {}, [data(SNAPSHOT)]),
    ("snapshots", "create", (INSTANCE_ID,), {}, [data({"snapshot_id": SNAPSHOT_ID}, 202)]),
    ("snapshots", "restore", (INSTANCE_ID, SNAPSHOT_ID), {}, [data(INSTANCE, 202)]),
    ("cmek", "list", (TENANT_ID,), {}, [data([])]),
    ("cmek", "get", (KEY["id"],), {}, [data(KEY)]),
    (
        "cmek",
        "create",
        (),
        {
            "name": "Key01",
            "key_id": KEY["key_id"],
            "tenant_id": TENANT_ID,
            "cloud_provider": "aws",
            "region": "us-west-2",
            "instance_type": "enterprise-db",
        },
        [data(KEY, 202)],
    ),
    ("cmek", "delete", (KEY["id"],), {}, [HttpResponse(204)]),
    (
        "graph_analytics",
        "list",
        (),
        {"tenant_id": TENANT_ID, "instance_id": INSTANCE_ID, "organization_id": "org"},
        [data([SESSION])],
    ),
    (
        "graph_analytics",
        "estimate_size",
        (),
        {"node_count": 1, "relationship_count": 2, "node_label_count": 3},
        [data({"estimated_memory": "1GB", "recommended_size": "2GB"})],
    ),
    (
        "graph_analytics",
        "create",
        (aura.GDSSessionConfig(name="s", memory="8GB", ttl="1h"),),
        {},
        [data(SESSION, 202)],
    ),
    ("graph_analytics", "get", (SESSION["id"],), {}, [data(SESSION)]),
    ("graph_analytics", "delete", (SESSION["id"],), {}, [data({"id": SESSION["id"]}, 202)]),
    ("prometheus", "fetch_raw_metrics", (METRICS_URL,), {}, [METRICS]),
    ("prometheus", "get_instance_health", (INSTANCE_ID, METRICS_URL), {}, [METRICS]),
]

# Methods without I/O. They are plain methods on both clients, and checked separately.
NO_IO_METHODS = {("prometheus", "get_metric_value")}


def _wire(transport: FakeTransport) -> list[tuple[str, str, dict[str, str], bytes | None]]:
    return [(r.method, r.url, dict(r.headers), r.body) for r in transport.requests]


def _comparable(result: object) -> object:
    if isinstance(result, aura.InstanceHealth):
        return dataclasses.replace(result, timestamp=dt.datetime(2000, 1, 1, tzinfo=dt.UTC))
    return result


def _public_methods(cls: type) -> dict[str, Callable[..., Any]]:
    return {
        name: member
        for name, member in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    }


@pytest.mark.parametrize(("sync_cls", "async_cls"), SERVICE_PAIRS, ids=lambda c: c.__name__)
def test_signatures_match(sync_cls: type, async_cls: type) -> None:
    sync_methods = _public_methods(sync_cls)
    async_methods = _public_methods(async_cls)
    assert sync_methods.keys() == async_methods.keys()
    for name, sync_method in sync_methods.items():
        async_method = async_methods[name]
        assert inspect.signature(sync_method) == inspect.signature(async_method), name
        assert inspect.iscoroutinefunction(async_method) != (
            (sync_cls.__name__, name) in {("PrometheusService", "get_metric_value")}
        ), f"{async_cls.__name__}.{name} should be async"
        assert not inspect.iscoroutinefunction(sync_method), name


def test_every_method_has_a_parity_case() -> None:
    client = aura.AuraClient(client_id="id", client_secret="secret", transport=FakeTransport())
    attribute_for = {
        type(getattr(client, attr)): attr
        for attr in ("tenants", "instances", "snapshots", "cmek", "graph_analytics", "prometheus")
    }
    expected = {
        (attribute_for[sync_cls], name)
        for sync_cls, _ in SERVICE_PAIRS
        for name in _public_methods(sync_cls)
    }
    covered = {(service, method) for service, method, *_ in CASES} | NO_IO_METHODS
    assert expected == covered


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("service", "method", "args", "kwargs", "replies"),
    CASES,
    ids=[f"{c[0]}.{c[1]}" for c in CASES],
)
async def test_async_matches_sync(
    service: str,
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    replies: list[HttpResponse],
) -> None:
    sync_transport = FakeTransport([token_response(), *replies])
    sync_client = aura.AuraClient(client_id="id", client_secret="secret", transport=sync_transport)
    sync_result = getattr(getattr(sync_client, service), method)(*args, **kwargs)

    async_transport = FakeAsyncTransport([token_response(), *replies])
    async_client = aura.AsyncAuraClient(
        client_id="id", client_secret="secret", transport=async_transport
    )
    async_result = await getattr(getattr(async_client, service), method)(*args, **kwargs)

    assert _wire(async_transport) == _wire(sync_transport)
    assert _comparable(async_result) == _comparable(sync_result)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("service", "method", "args", "kwargs"),
    [
        ("instances", "get", ("bad",), {}),
        ("instances", "update", (INSTANCE_ID,), {}),
        ("instances", "upgrade", (INSTANCE_ID,), {"memory": "16GB"}),
        ("snapshots", "list", (INSTANCE_ID, "2026-01-02"), {}),
        ("cmek", "get", ("",), {}),
        ("graph_analytics", "list", (), {"tenant_id": "bad"}),
        ("prometheus", "fetch_raw_metrics", ("https://evil.example.com/metrics",), {}),
        ("prometheus", "get_instance_health", ("bad", METRICS_URL), {}),
    ],
)
async def test_async_validates_like_sync(
    service: str, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    sync_client = aura.AuraClient(client_id="id", client_secret="secret", transport=FakeTransport())
    with pytest.raises(aura.AuraValidationError) as sync_error:
        getattr(getattr(sync_client, service), method)(*args, **kwargs)

    async_transport = FakeAsyncTransport()
    async_client = aura.AsyncAuraClient(
        client_id="id", client_secret="secret", transport=async_transport
    )
    with pytest.raises(aura.AuraValidationError) as async_error:
        await getattr(getattr(async_client, service), method)(*args, **kwargs)

    assert str(async_error.value) == str(sync_error.value)
    assert async_transport.requests == []


def test_get_metric_value_is_shared() -> None:
    client = aura.AsyncAuraClient(
        client_id="id", client_secret="secret", transport=FakeAsyncTransport()
    )
    metrics = aura.PrometheusMetrics(metrics={"m": (aura.PrometheusMetric(name="m", value=2.0),)})
    assert client.prometheus.get_metric_value(metrics, "m") == 2.0
