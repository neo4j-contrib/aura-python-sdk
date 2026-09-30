import dataclasses

import pytest

import aura_python_sdk as aura
from aura_python_sdk import models
from aura_python_sdk._internal._serde import from_json, to_json

CREATED = {
    "id": "db1d1234",
    "name": "Instance01",
    "tenant_id": "t",
    "cloud_provider": "gcp",
    "region": "europe-west1",
    "type": "enterprise-db",
    "connection_url": "neo4j+s://db1d1234.databases.neo4j.io",
    "username": "neo4j",
    "password": "letMeIn123!",
}


def test_created_instance_password_is_redacted_from_repr() -> None:
    created = from_json(models.CreatedInstance, CREATED)
    assert created.password == "letMeIn123!"
    assert "letMeIn123!" not in repr(created)
    assert "letMeIn123!" not in str(created)


def test_models_are_frozen() -> None:
    summary = models.TenantSummary(id="t", name="n")
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.name = "other"  # type: ignore[misc]


def test_models_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        models.TenantSummary("t", "n")  # type: ignore[call-arg]


def test_instance_status_covers_spec_and_go_values() -> None:
    spec_values = {
        "creating", "destroying", "running", "pausing", "paused", "suspending", "suspended",
        "resuming", "loading", "loading failed", "restoring", "updating", "overwriting",
    }  # fmt: skip
    assert {s.value for s in models.InstanceStatus} == spec_values | {"stopped", "available"}


def test_free_instance_without_storage_and_with_graph_counts() -> None:
    instance = from_json(
        models.Instance,
        {
            "id": "abcd1234",
            "name": "Free",
            "status": "running",
            "tenant_id": "t",
            "cloud_provider": "gcp",
            "connection_url": "neo4j+s://abcd1234.databases.neo4j.io",
            "region": "europe-west1",
            "type": "free-db",
            "memory": "1GB",
            "graph_nodes": "1234",
            "graph_relationships": "5678",
        },
    )
    assert instance.storage is None
    assert instance.type is models.InstanceType.FREE_DB
    assert (instance.graph_nodes, instance.graph_relationships) == (1234, 5678)


def test_gds_ttl_integer_is_accepted_as_string() -> None:
    session = from_json(
        models.GDSSession,
        {"id": "s", "name": "n", "memory": "8GB", "host": "h", "tenant_id": "t", "user_id": "u",
         "ttl": 3600},
    )  # fmt: skip
    assert session.ttl == "3600"


def test_instance_config_to_json_omits_unset_options() -> None:
    config = models.InstanceConfig(
        name="Instance01",
        tenant_id="t",
        cloud_provider=models.CloudProvider.GCP,
        region="europe-west1",
        type=models.InstanceType.ENTERPRISE_DB,
        version="5",
        memory="8GB",
        vector_optimized=False,
    )
    assert to_json(config) == {
        "name": "Instance01",
        "tenant_id": "t",
        "cloud_provider": "gcp",
        "region": "europe-west1",
        "type": "enterprise-db",
        "version": "5",
        "memory": "8GB",
        "vector_optimized": False,
    }


def test_gds_session_config_to_json() -> None:
    config = models.GDSSessionConfig(name="s", memory="8GB", ttl="1h", cloud_provider="aws")
    assert to_json(config) == {"name": "s", "memory": "8GB", "ttl": "1h", "cloud_provider": "aws"}


def test_all_models_exported_at_top_level() -> None:
    for name in models.__all__:
        assert getattr(aura, name) is getattr(models, name)
        assert name in aura.__all__


@pytest.mark.parametrize("payload", [{"connection_url": None}, {}])
def test_instance_connection_url_may_be_null_or_missing(payload: dict[str, object]) -> None:
    # The spec marks it required, but the live API returns null for some instances.
    base = {
        "id": "abcd1234",
        "name": "x",
        "status": "creating",
        "tenant_id": "t",
        "cloud_provider": "gcp",
        "region": "europe-west1",
        "type": "enterprise-db",
        "memory": "8GB",
    }
    assert from_json(models.Instance, {**base, **payload}).connection_url is None
