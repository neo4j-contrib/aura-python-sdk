import pytest

from aura_python_sdk import AuraValidationError, InstanceType, Tenant, TenantSummary
from tests.unit.conftest import BASE, TENANT_ID, Api


def test_list(api: Api) -> None:
    api.reply(200, {"data": [{"id": TENANT_ID, "name": "Production"}]})
    assert api.client.tenants.list() == [TenantSummary(id=TENANT_ID, name="Production")]
    assert (api.request.method, api.request.url) == ("GET", f"{BASE}/tenants")


def test_get(api: Api) -> None:
    config = {
        "cloud_provider": "gcp",
        "region": "europe-west1",
        "region_name": "Belgium (europe-west1)",
        "type": "enterprise-db",
        "memory": "8GB",
        "storage": "16GB",
        "version": "5",
    }
    api.reply(
        200, {"data": {"id": TENANT_ID, "name": "Production", "instance_configurations": [config]}}
    )

    tenant = api.client.tenants.get(TENANT_ID)

    assert isinstance(tenant, Tenant)
    assert tenant.instance_configurations[0].type is InstanceType.ENTERPRISE_DB
    assert api.request.url == f"{BASE}/tenants/{TENANT_ID}"


def test_get_metrics_integration(api: Api) -> None:
    api.reply(
        200, {"data": {"endpoint": "https://customer-metrics-api.neo4j.io/api/v1/abc/metrics"}}
    )
    result = api.client.tenants.get_metrics_integration(TENANT_ID)
    assert result.endpoint.endswith("/metrics")
    assert api.request.url == f"{BASE}/tenants/{TENANT_ID}/metrics-integration"


@pytest.mark.parametrize("call", ["get", "get_metrics_integration"])
def test_invalid_tenant_id_sends_nothing(api: Api, call: str) -> None:
    with pytest.raises(AuraValidationError, match="tenant ID"):
        getattr(api.client.tenants, call)("not-a-uuid")
    api.assert_no_request()
