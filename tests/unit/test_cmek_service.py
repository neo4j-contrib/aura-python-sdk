from typing import Any

import pytest

from aura_python_sdk import (
    AuraValidationError,
    BadRequestError,
    CloudProvider,
    CustomerManagedKey,
    CustomerManagedKeySummary,
    HttpResponse,
    InstanceType,
)
from tests.unit.conftest import BASE, TENANT_ID, Api

KEY = {"id": "8c764aed-8eb3-4a1c-92f6-e4ef0c7a6ed9", "name": "Key01", "tenant_id": TENANT_ID}


def test_list(api: Api) -> None:
    api.reply(200, {"data": [KEY]})
    assert api.client.cmek.list() == [CustomerManagedKeySummary(**KEY)]
    assert api.request.url == f"{BASE}/customer-managed-keys"


def test_list_filtered_by_tenant(api: Api) -> None:
    api.reply(200, {"data": [KEY]})
    api.client.cmek.list(TENANT_ID)
    assert api.request.url == f"{BASE}/customer-managed-keys?tenantId={TENANT_ID}"


def test_list_invalid_tenant_sends_nothing(api: Api) -> None:
    with pytest.raises(AuraValidationError, match="tenant ID"):
        api.client.cmek.list("bad")
    api.assert_no_request()


FULL_KEY = {
    **KEY,
    "cloud_provider": "aws",
    "region": "us-west-2",
    "instance_type": "enterprise-db",
    "key_id": "arn:aws:kms:us-west-2:111122223333:key/1234abcd-12ab-34cd-56ef-1234567890ab",
    "status": "pending",
    "created": "2024-01-31T14:06:57Z",
}

CREATE_KWARGS = {
    "name": "Production Key",
    "key_id": FULL_KEY["key_id"],
    "tenant_id": TENANT_ID,
    "cloud_provider": CloudProvider.AWS,
    "region": "us-west-2",
    "instance_type": InstanceType.ENTERPRISE_DB,
}


def test_get(api: Api) -> None:
    api.reply(200, {"data": FULL_KEY})
    key = api.client.cmek.get(KEY["id"])
    assert isinstance(key, CustomerManagedKey)
    assert key.cloud_provider is CloudProvider.AWS
    assert api.request.url == f"{BASE}/customer-managed-keys/{KEY['id']}"


def test_create(api: Api) -> None:
    api.reply(202, {"data": FULL_KEY})
    key = api.client.cmek.create(**CREATE_KWARGS)
    assert key.status == "pending"
    assert (api.request.method, api.request.url) == ("POST", f"{BASE}/customer-managed-keys")
    # Matches the spec's "Creates a Customer Managed Key" request example.
    assert api.body == {
        "name": "Production Key",
        "key_id": FULL_KEY["key_id"],
        "tenant_id": TENANT_ID,
        "cloud_provider": "aws",
        "region": "us-west-2",
        "instance_type": "enterprise-db",
    }


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"name": ""}, "key name must not be empty"),
        ({"name": "k" * 31}, "at most 30 characters"),
        ({"name": "Key "}, "leading or trailing whitespace"),
        ({"key_id": ""}, "cloud provider key ID"),
        ({"tenant_id": "bad"}, "tenant ID"),
        ({"cloud_provider": ""}, "cloud provider must not be empty"),
        ({"region": ""}, "region"),
        ({"instance_type": ""}, "instance type"),
    ],
)
def test_create_validation(api: Api, override: dict[str, Any], message: str) -> None:
    with pytest.raises(AuraValidationError, match=message):
        api.client.cmek.create(**{**CREATE_KWARGS, **override})
    api.assert_no_request()


def test_delete(api: Api) -> None:
    api.transport.queue(HttpResponse(204))
    api.client.cmek.delete(KEY["id"])
    assert (api.request.method, api.request.url) == (
        "DELETE",
        f"{BASE}/customer-managed-keys/{KEY['id']}",
    )


def test_delete_active_key_is_bad_request(api: Api) -> None:
    api.reply(
        400,
        {
            "errors": [
                {
                    "message": "The key is linked to an active instance.",
                    "reason": "encryption-key-is-active",
                }
            ]
        },
    )
    with pytest.raises(BadRequestError) as info:
        api.client.cmek.delete(KEY["id"])
    assert info.value.details[0].reason == "encryption-key-is-active"


@pytest.mark.parametrize("call", ["get", "delete"])
def test_empty_key_id(api: Api, call: str) -> None:
    with pytest.raises(AuraValidationError, match="customer managed key ID must not be empty"):
        getattr(api.client.cmek, call)("")
    api.assert_no_request()


def test_key_id_is_path_encoded(api: Api) -> None:
    api.reply(200, {"data": FULL_KEY})
    api.client.cmek.get("a/b")
    assert api.request.url == f"{BASE}/customer-managed-keys/a%2Fb"
