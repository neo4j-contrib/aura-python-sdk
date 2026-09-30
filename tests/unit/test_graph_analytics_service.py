from typing import Any

import pytest

from aura_python_sdk import (
    AuraValidationError,
    CloudProvider,
    DeletedGDSSession,
    GDSSessionConfig,
    GDSSessionSizeEstimate,
    GDSSessionStatus,
)
from tests.unit.conftest import BASE, INSTANCE_ID, SESSION, TENANT_ID, Api

SESSIONS = f"{BASE}/graph-analytics/sessions"


def test_list(api: Api) -> None:
    api.reply(200, {"data": [SESSION]})
    [session] = api.client.graph_analytics.list()
    assert session.status is GDSSessionStatus.READY
    assert api.request.url == SESSIONS


def test_get(api: Api) -> None:
    api.reply(200, {"data": SESSION})
    assert api.client.graph_analytics.get(SESSION["id"]).ttl == "20m0s"
    assert api.request.url == f"{SESSIONS}/{SESSION['id']}"


def test_session_id_is_path_encoded(api: Api) -> None:
    api.reply(200, {"data": SESSION})
    api.client.graph_analytics.get("../instances")
    assert api.request.url == f"{SESSIONS}/..%2Finstances"


def test_delete(api: Api) -> None:
    api.reply(202, {"data": {"id": SESSION["id"]}})
    assert api.client.graph_analytics.delete(SESSION["id"]) == DeletedGDSSession(id=SESSION["id"])
    assert (api.request.method, api.request.url) == ("DELETE", f"{SESSIONS}/{SESSION['id']}")


@pytest.mark.parametrize("call", ["get", "delete"])
def test_empty_session_id(api: Api, call: str) -> None:
    with pytest.raises(AuraValidationError, match="GDS session ID must not be empty"):
        getattr(api.client.graph_analytics, call)("")
    api.assert_no_request()


@pytest.mark.parametrize("status", [200, 202])
def test_create(api: Api, status: int) -> None:
    api.reply(status, {"data": SESSION})
    config = GDSSessionConfig(
        name="people-and-fruit",
        memory="8GB",
        ttl="1h",
        tenant_id=TENANT_ID,
        cloud_provider=CloudProvider.AZURE,
        region="francecentral",
    )
    session = api.client.graph_analytics.create(config)
    assert session.id == SESSION["id"]
    assert (api.request.method, api.request.url) == ("POST", SESSIONS)
    assert api.body == {
        "name": "people-and-fruit",
        "memory": "8GB",
        "ttl": "1h",
        "tenant_id": TENANT_ID,
        "cloud_provider": "azure",
        "region": "francecentral",
    }


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"name": "people", "memory": "8GB", "a": 1}, "config must be a GDSSessionConfig"),
        (GDSSessionConfig(name="", memory="8GB"), "session name must not be empty"),
        (GDSSessionConfig(name="s", memory=""), "memory must not be empty"),
        (GDSSessionConfig(name="s", memory="8GB", tenant_id="bad"), "tenant ID"),
        (GDSSessionConfig(name="s", memory="8GB", instance_id="bad"), "instance ID"),
    ],
)
def test_create_validation(api: Api, config: Any, message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.graph_analytics.create(config)
    api.assert_no_request()


def test_create_attached_to_instance(api: Api) -> None:
    api.reply(202, {"data": SESSION})
    config = GDSSessionConfig(
        name="s",
        memory="4GB",
        instance_id=INSTANCE_ID,
        database_uuid="ea408a62-c991-490c-96db-2b947003eece",
    )
    api.client.graph_analytics.create(config)
    assert api.body["instance_id"] == INSTANCE_ID


def test_estimate_size(api: Api) -> None:
    api.reply(200, {"data": {"estimated_memory": "6GB", "recommended_size": "8GB"}})
    estimate = api.client.graph_analytics.estimate_size(
        node_count=1_000_000,
        relationship_count=5_000_000,
        node_property_count=512,
        node_label_count=3,
        relationship_property_count=5,
        algorithm_categories=["similarity", "community-detection"],
    )
    assert estimate == GDSSessionSizeEstimate(estimated_memory="6GB", recommended_size="8GB")
    assert (api.request.method, api.request.url) == ("POST", f"{SESSIONS}/sizing")
    assert api.body == {
        "node_count": 1_000_000,
        "relationship_count": 5_000_000,
        "node_property_count": 512,
        "node_label_count": 3,
        "relationship_property_count": 5,
        "algorithm_categories": ["similarity", "community-detection"],
    }


def test_estimate_size_minimal(api: Api) -> None:
    api.reply(200, {"data": {"estimated_memory": "1GB", "recommended_size": "2GB"}})
    api.client.graph_analytics.estimate_size(node_count=10, relationship_count=0)
    assert api.body == {"node_count": 10, "relationship_count": 0}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"node_count": -1, "relationship_count": 1}, "node count"),
        ({"node_count": 1, "relationship_count": 1.5}, "relationship count"),
        ({"node_count": 1, "relationship_count": 1, "node_label_count": -3}, "node label count"),
        (
            {"node_count": 1, "relationship_count": 1, "algorithm_categories": "similarity"},
            "sequence",
        ),
        (
            {"node_count": 1, "relationship_count": 1, "algorithm_categories": [""]},
            "algorithm categories entry",
        ),
    ],
)
def test_estimate_size_validation(api: Api, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.graph_analytics.estimate_size(**kwargs)
    api.assert_no_request()


def test_list_with_filters(api: Api) -> None:
    api.reply(200, {"data": []})
    api.client.graph_analytics.list(
        tenant_id=TENANT_ID, instance_id=INSTANCE_ID, organization_id="org-1"
    )
    assert api.request.url == (
        f"{SESSIONS}?tenantId={TENANT_ID}&instanceId={INSTANCE_ID}&organizationId=org-1"
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tenant_id": "bad"}, "tenant ID"),
        ({"instance_id": "bad"}, "instance ID"),
        ({"organization_id": ""}, "organization ID"),
    ],
)
def test_list_filter_validation(api: Api, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.graph_analytics.list(**kwargs)
    api.assert_no_request()
