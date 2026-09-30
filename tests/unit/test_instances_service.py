from dataclasses import replace
from typing import Any

import pytest

from aura_python_sdk import (
    AuraValidationError,
    CDCEnrichmentMode,
    CloudProvider,
    ConflictError,
    CreatedInstance,
    Instance,
    InstanceConfig,
    InstanceStatus,
    InstanceSummary,
    InstanceType,
    NotFoundError,
)
from tests.unit.conftest import (
    BASE,
    INSTANCE,
    INSTANCE_ID,
    OTHER_INSTANCE_ID,
    SNAPSHOT_ID,
    TENANT_ID,
    Api,
)

CONFIG = InstanceConfig(
    name="Instance01",
    tenant_id=TENANT_ID,
    cloud_provider=CloudProvider.GCP,
    region="europe-west1",
    type=InstanceType.ENTERPRISE_DB,
    version="5",
    memory="8GB",
)

CONFIG_JSON = {
    "name": "Instance01",
    "tenant_id": TENANT_ID,
    "cloud_provider": "gcp",
    "region": "europe-west1",
    "type": "enterprise-db",
    "version": "5",
    "memory": "8GB",
}

CREATED = {
    "id": "db1d1234",
    "name": "Instance01",
    "tenant_id": TENANT_ID,
    "cloud_provider": "gcp",
    "region": "europe-west1",
    "type": "enterprise-db",
    "connection_url": "neo4j+s://db1d1234.databases.neo4j.io",
    "username": "neo4j",
    "password": "letMeIn123!",
    "created_at": "2023-01-20T13:44:42Z",
}


def test_list(api: Api) -> None:
    api.reply(
        200,
        {
            "data": [
                {"id": INSTANCE_ID, "name": "P", "tenant_id": TENANT_ID, "cloud_provider": "aws"}
            ]
        },
    )
    [summary] = api.client.instances.list()
    assert isinstance(summary, InstanceSummary)
    assert summary.cloud_provider is CloudProvider.AWS
    assert (api.request.method, api.request.url) == ("GET", f"{BASE}/instances")


def test_get(api: Api) -> None:
    api.reply(200, {"data": INSTANCE})
    instance = api.client.instances.get(INSTANCE_ID)
    assert isinstance(instance, Instance)
    assert instance.status is InstanceStatus.RUNNING
    assert api.request.url == f"{BASE}/instances/{INSTANCE_ID}"


def test_get_not_found(api: Api) -> None:
    api.reply(404, {"errors": [{"message": "Instance not found", "reason": "instance-not-found"}]})
    with pytest.raises(NotFoundError, match="Instance not found"):
        api.client.instances.get(INSTANCE_ID)


def test_create(api: Api) -> None:
    api.reply(202, {"data": CREATED})
    created = api.client.instances.create(CONFIG)

    assert isinstance(created, CreatedInstance)
    assert created.password == "letMeIn123!"
    assert (api.request.method, api.request.url) == ("POST", f"{BASE}/instances")
    assert api.body == CONFIG_JSON


def test_create_sends_optional_fields_when_set(api: Api) -> None:
    api.reply(202, {"data": CREATED})
    key_id = "8c764aed-8eb3-4a1c-92f6-e4ef0c7a6ed9"
    config = replace(
        CONFIG, vector_optimized=True, graph_analytics_plugin=False, customer_managed_key_id=key_id
    )
    api.client.instances.create(config)
    assert api.body == {
        **CONFIG_JSON,
        "vector_optimized": True,
        "graph_analytics_plugin": False,
        "customer_managed_key_id": key_id,
    }


def test_create_from_instance(api: Api) -> None:
    api.reply(202, {"data": CREATED})
    api.client.instances.create_from_instance(CONFIG, source_instance_id=OTHER_INSTANCE_ID)
    assert api.body == {**CONFIG_JSON, "source_instance_id": OTHER_INSTANCE_ID}


def test_create_from_snapshot(api: Api) -> None:
    api.reply(202, {"data": CREATED})
    api.client.instances.create_from_snapshot(
        CONFIG, source_instance_id=OTHER_INSTANCE_ID, source_snapshot_id=SNAPSHOT_ID
    )
    assert api.body == {
        **CONFIG_JSON,
        "source_instance_id": OTHER_INSTANCE_ID,
        "source_snapshot_id": SNAPSHOT_ID,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": ""}, "instance name must not be empty"),
        ({"name": "x" * 31}, "at most 30 characters"),
        ({"tenant_id": ""}, "tenant ID must not be empty"),
        ({"tenant_id": "abc"}, "tenant ID must be a valid UUID"),
        ({"cloud_provider": ""}, "cloud provider must not be empty"),
        ({"region": ""}, "region must not be empty"),
        ({"type": ""}, "instance type must not be empty"),
        ({"version": ""}, "version must not be empty"),
        ({"memory": ""}, "memory must not be empty"),
        ({"customer_managed_key_id": ""}, "customer managed key ID must not be empty"),
    ],
)
def test_create_validation_matches_go(api: Api, overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.instances.create(replace(CONFIG, **overrides))
    api.assert_no_request()


def test_create_requires_instance_config(api: Api) -> None:
    with pytest.raises(AuraValidationError, match="config must be an InstanceConfig"):
        api.client.instances.create(CONFIG_JSON)  # type: ignore[arg-type]
    api.assert_no_request()


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.create_from_instance(CONFIG, source_instance_id=""),
        lambda s: s.create_from_instance(CONFIG, source_instance_id="bad"),
        lambda s: s.create_from_snapshot(
            CONFIG, source_instance_id="bad", source_snapshot_id=SNAPSHOT_ID
        ),
        lambda s: s.create_from_snapshot(
            CONFIG, source_instance_id=OTHER_INSTANCE_ID, source_snapshot_id="bad"
        ),
        lambda s: s.create_from_snapshot(
            CONFIG, source_instance_id=OTHER_INSTANCE_ID, source_snapshot_id=""
        ),
    ],
)
def test_create_from_source_validation(api: Api, call: Any) -> None:
    with pytest.raises(AuraValidationError, match=r"source (instance|snapshot) ID"):
        call(api.client.instances)
    api.assert_no_request()


def test_update(api: Api) -> None:
    api.reply(202, {"data": {**INSTANCE, "status": "updating"}})
    instance = api.client.instances.update(
        INSTANCE_ID,
        name="Renamed",
        memory="16GB",
        cdc_enrichment_mode=CDCEnrichmentMode.FULL,
        secondaries_count=2,
    )
    assert instance.status is InstanceStatus.UPDATING
    assert (api.request.method, api.request.url) == ("PATCH", f"{BASE}/instances/{INSTANCE_ID}")
    assert api.body == {
        "name": "Renamed",
        "memory": "16GB",
        "cdc_enrichment_mode": "FULL",
        "secondaries_count": 2,
    }


def test_update_sends_only_given_fields(api: Api) -> None:
    api.reply(200, {"data": INSTANCE})
    api.client.instances.update(INSTANCE_ID, secondaries_count=0)
    assert api.body == {"secondaries_count": 0}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "at least one field"),
        ({"name": "x" * 31}, "at most 30 characters"),
        ({"memory": ""}, "memory must not be empty"),
        ({"cdc_enrichment_mode": ""}, "CDC enrichment mode"),
        ({"secondaries_count": -1}, "secondaries count"),
    ],
)
def test_update_validation(api: Api, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.instances.update(INSTANCE_ID, **kwargs)
    api.assert_no_request()


def test_delete(api: Api) -> None:
    api.reply(202, {"data": {**INSTANCE, "status": "destroying"}})
    instance = api.client.instances.delete(INSTANCE_ID)
    assert instance.status is InstanceStatus.DESTROYING
    assert (api.request.method, api.request.url) == ("DELETE", f"{BASE}/instances/{INSTANCE_ID}")
    assert api.request.body is None


@pytest.mark.parametrize(("action", "status"), [("pause", "pausing"), ("resume", "resuming")])
def test_pause_and_resume(api: Api, action: str, status: str) -> None:
    api.reply(202, {"data": {**INSTANCE, "status": status}})
    instance = getattr(api.client.instances, action)(INSTANCE_ID)
    assert instance.status == status
    assert (api.request.method, api.request.url) == (
        "POST",
        f"{BASE}/instances/{INSTANCE_ID}/{action}",
    )
    assert api.request.body is None


def test_pause_conflict(api: Api) -> None:
    api.reply(409, {"errors": [{"message": "Instance is not running", "reason": "conflict"}]})
    with pytest.raises(ConflictError):
        api.client.instances.pause(INSTANCE_ID)


def test_overwrite_from_instance(api: Api) -> None:
    api.reply(202, {"data": {**INSTANCE, "status": "overwriting"}})
    instance = api.client.instances.overwrite_from_instance(
        INSTANCE_ID, source_instance_id=OTHER_INSTANCE_ID
    )
    assert instance.status is InstanceStatus.OVERWRITING
    assert api.request.url == f"{BASE}/instances/{INSTANCE_ID}/overwrite"
    assert api.body == {"source_instance_id": OTHER_INSTANCE_ID}


def test_overwrite_from_snapshot(api: Api) -> None:
    api.reply(202, {"data": {**INSTANCE, "status": "overwriting"}})
    api.client.instances.overwrite_from_snapshot(INSTANCE_ID, source_snapshot_id=SNAPSHOT_ID)
    assert api.body == {"source_snapshot_id": SNAPSHOT_ID}


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.get("nope"),
        lambda s: s.delete(""),
        lambda s: s.pause("../../x"),
        lambda s: s.resume("12345"),
        lambda s: s.update("bad", name="x"),
        lambda s: s.overwrite_from_instance("bad", source_instance_id=OTHER_INSTANCE_ID),
        lambda s: s.overwrite_from_instance(INSTANCE_ID, source_instance_id="bad"),
        lambda s: s.overwrite_from_snapshot(INSTANCE_ID, source_snapshot_id="bad"),
    ],
)
def test_invalid_ids_send_nothing(api: Api, call: Any) -> None:
    with pytest.raises(AuraValidationError):
        call(api.client.instances)
    api.assert_no_request()


# --- Phase 5: spec coverage beyond the Go SDK ---


def test_list_filtered_by_tenant(api: Api) -> None:
    api.reply(200, {"data": []})
    api.client.instances.list(tenant_id=TENANT_ID)
    assert api.request.url == f"{BASE}/instances?tenantId={TENANT_ID}"


def test_list_invalid_tenant_sends_nothing(api: Api) -> None:
    with pytest.raises(AuraValidationError, match="tenant ID"):
        api.client.instances.list(tenant_id="bad")
    api.assert_no_request()


def test_update_new_spec_fields(api: Api) -> None:
    api.reply(202, {"data": INSTANCE})
    api.client.instances.update(
        INSTANCE_ID, storage="32GB", vector_optimized=True, graph_analytics_plugin=False
    )
    assert api.body == {
        "storage": "32GB",
        "vector_optimized": True,
        "graph_analytics_plugin": False,
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"storage": ""}, "storage must not be empty"),
        ({"vector_optimized": "yes"}, "vector optimized must be True or False"),
        ({"graph_analytics_plugin": 1}, "graph analytics plugin must be True or False"),
        ({"name": " padded"}, "leading or trailing whitespace"),
    ],
)
def test_update_new_field_validation(api: Api, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.instances.update(INSTANCE_ID, **kwargs)
    api.assert_no_request()


def test_estimate_size(api: Api) -> None:
    api.reply(
        200,
        {
            "data": {
                "did_exceed_maximum": False,
                "min_required_memory": "14GB",
                "recommended_size": "16GB",
            }
        },
    )
    estimate = api.client.instances.estimate_size(
        node_count=1_000_000,
        relationship_count=5_000_000,
        instance_type=InstanceType.PROFESSIONAL_DS,
        algorithm_categories=["pathfinding", "community-detection"],
    )
    assert estimate.recommended_size == "16GB"
    assert estimate.did_exceed_maximum is False
    assert (api.request.method, api.request.url) == ("POST", f"{BASE}/instances/sizing")
    assert api.body == {
        "node_count": 1_000_000,
        "relationship_count": 5_000_000,
        "instance_type": "professional-ds",
        "algorithm_categories": ["pathfinding", "community-detection"],
    }


def test_estimate_size_minimal(api: Api) -> None:
    api.reply(
        200,
        {
            "data": {
                "did_exceed_maximum": True,
                "min_required_memory": "1TB",
                "recommended_size": "1TB",
            }
        },
    )
    api.client.instances.estimate_size(node_count=1, relationship_count=2)
    assert api.body == {"node_count": 1, "relationship_count": 2}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"node_count": -1, "relationship_count": 0}, "node count"),
        ({"node_count": 1, "relationship_count": None}, "relationship count"),
        ({"node_count": 1, "relationship_count": 1, "instance_type": ""}, "instance type"),
        (
            {"node_count": 1, "relationship_count": 1, "algorithm_categories": "pathfinding"},
            "sequence",
        ),
    ],
)
def test_estimate_size_validation(api: Api, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.instances.estimate_size(**kwargs)
    api.assert_no_request()


def test_upgrade_keeping_size(api: Api) -> None:
    api.reply(200, {"data": {**INSTANCE, "type": "business-critical"}})
    instance = api.client.instances.upgrade(INSTANCE_ID)
    assert instance.type is InstanceType.BUSINESS_CRITICAL
    assert (api.request.method, api.request.url) == (
        "POST",
        f"{BASE}/instances/{INSTANCE_ID}/upgrade",
    )
    assert api.body == {}


def test_upgrade_with_resize(api: Api) -> None:
    api.reply(200, {"data": INSTANCE})
    api.client.instances.upgrade(INSTANCE_ID, memory="16GB", storage="32GB")
    assert api.body == {"memory": "16GB", "storage": "32GB"}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"memory": "16GB"}, "both memory and storage"),
        ({"storage": "32GB"}, "both memory and storage"),
        ({"memory": "", "storage": "32GB"}, "memory must not be empty"),
    ],
)
def test_upgrade_validation(api: Api, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.instances.upgrade(INSTANCE_ID, **kwargs)
    api.assert_no_request()


def test_upgrade_invalid_id(api: Api) -> None:
    with pytest.raises(AuraValidationError, match="instance ID"):
        api.client.instances.upgrade("bad")
    api.assert_no_request()
