"""``client.cmek`` (Go: CMEKService)."""

from __future__ import annotations

import builtins

from aura_python_sdk import _validation as validate
from aura_python_sdk._internal._call import Call, many, nothing, one
from aura_python_sdk._internal._request import build_path
from aura_python_sdk._internal._serde import to_json
from aura_python_sdk.models._common import CloudProvider, InstanceType
from aura_python_sdk.models.cmek import CustomerManagedKey, CustomerManagedKeySummary
from aura_python_sdk.services._base import TENANT_ID_PARAM, AsyncService, Service

_KEYS = "customer-managed-keys"

# --- Operations (validation, request and parsing; no I/O) ---


def _list(tenant_id: str | None) -> Call[list[CustomerManagedKeySummary]]:
    if tenant_id is not None:
        tenant_id = validate.tenant_id(tenant_id)
    return Call(
        method="GET",
        path=_KEYS,
        params={TENANT_ID_PARAM: tenant_id},
        parse=many(CustomerManagedKeySummary),
        describe="listing customer managed keys",
        context={"tenant_id": tenant_id},
    )


def _get(key_id: str) -> Call[CustomerManagedKey]:
    key_id = validate.require_non_empty("customer managed key ID", key_id)
    return Call(
        method="GET",
        path=build_path(_KEYS, key_id),
        parse=one(CustomerManagedKey),
        describe="getting customer managed key",
        context={"key_id": key_id},
    )


def _create(
    *,
    name: str,
    key_id: str,
    tenant_id: str,
    cloud_provider: CloudProvider | str,
    region: str,
    instance_type: InstanceType | str,
) -> Call[CustomerManagedKey]:
    body = {
        "name": validate.display_name("key name", name),
        "key_id": validate.require_non_empty("cloud provider key ID", key_id),
        "tenant_id": validate.tenant_id(tenant_id),
        "cloud_provider": validate.require_non_empty("cloud provider", cloud_provider),
        "region": validate.require_non_empty("region", region),
        "instance_type": validate.require_non_empty("instance type", instance_type),
    }
    return Call(
        method="POST",
        path=_KEYS,
        json_body=to_json(body),
        parse=one(CustomerManagedKey),
        describe="creating customer managed key",
        done="customer managed key created",
        context={"key_name": name, "tenant_id": tenant_id},
    )


def _delete(key_id: str) -> Call[None]:
    key_id = validate.require_non_empty("customer managed key ID", key_id)
    return Call(
        method="DELETE",
        path=build_path(_KEYS, key_id),
        parse=nothing,
        describe="deleting customer managed key",
        done="customer managed key deleted",
        context={"key_id": key_id},
    )


# --- Services ---


class CMEKService(Service):
    """Customer-managed encryption keys.

    Each method lists the errors specific to it. The errors any call can raise are listed on
    :class:`~aura_python_sdk.AuraClient`.
    """

    def list(self, *, tenant_id: str | None = None) -> builtins.list[CustomerManagedKeySummary]:
        """Every key the credentials can access, optionally only those in one tenant.

        Raises:
            AuraValidationError: ``tenant_id`` is invalid; nothing was sent.
        """
        return self._run(_list(tenant_id))

    def get(self, key_id: str) -> CustomerManagedKey:
        """Full details of one key. ``key_id`` is the Aura key ID, not the cloud provider's.

        Raises:
            AuraValidationError: ``key_id`` is invalid; nothing was sent.
            NotFoundError: The key doesn't exist.
        """
        return self._run(_get(key_id))

    def create(
        self,
        *,
        name: str,
        key_id: str,
        tenant_id: str,
        cloud_provider: CloudProvider | str,
        region: str,
        instance_type: InstanceType | str,
    ) -> CustomerManagedKey:
        """Register a key from your cloud provider with Aura.

        ``key_id`` is the key's ID in the cloud provider (the key ARN on AWS). The key can then
        encrypt new ``instance_type`` instances in ``region``. It starts in ``pending`` status.

        Raises:
            AuraValidationError: An argument is invalid; nothing was sent.
        """
        return self._run(
            _create(
                name=name,
                key_id=key_id,
                tenant_id=tenant_id,
                cloud_provider=cloud_provider,
                region=region,
                instance_type=instance_type,
            )
        )

    def delete(self, key_id: str) -> None:
        """Delete a key. The API refuses if any instance still uses it.

        Raises:
            AuraValidationError: ``key_id`` is invalid; nothing was sent.
            NotFoundError: The key doesn't exist.
            AuraAPIError: The key is still used by an instance.
        """
        self._run(_delete(key_id))


class AsyncCMEKService(AsyncService):
    """Async version of :class:`CMEKService`, with the same arguments and behaviour."""

    async def list(
        self, *, tenant_id: str | None = None
    ) -> builtins.list[CustomerManagedKeySummary]:
        """See :meth:`CMEKService.list`."""
        return await self._run(_list(tenant_id))

    async def get(self, key_id: str) -> CustomerManagedKey:
        """See :meth:`CMEKService.get`."""
        return await self._run(_get(key_id))

    async def create(
        self,
        *,
        name: str,
        key_id: str,
        tenant_id: str,
        cloud_provider: CloudProvider | str,
        region: str,
        instance_type: InstanceType | str,
    ) -> CustomerManagedKey:
        """See :meth:`CMEKService.create`."""
        return await self._run(
            _create(
                name=name,
                key_id=key_id,
                tenant_id=tenant_id,
                cloud_provider=cloud_provider,
                region=region,
                instance_type=instance_type,
            )
        )

    async def delete(self, key_id: str) -> None:
        """See :meth:`CMEKService.delete`."""
        await self._run(_delete(key_id))
