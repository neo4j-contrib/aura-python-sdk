"""``client.tenants`` (Go: TenantService)."""

from __future__ import annotations

import builtins

from aura_python_sdk import _validation as validate
from aura_python_sdk._internal._call import Call, many, one
from aura_python_sdk._internal._request import build_path
from aura_python_sdk.models.tenants import MetricsIntegration, Tenant, TenantSummary
from aura_python_sdk.services._base import AsyncService, Service

# --- Operations (validation, request and parsing; no I/O) ---


def _list() -> Call[list[TenantSummary]]:
    return Call(method="GET", path="tenants", parse=many(TenantSummary), describe="listing tenants")


def _get(tenant_id: str) -> Call[Tenant]:
    tenant_id = validate.tenant_id(tenant_id)
    return Call(
        method="GET",
        path=build_path("tenants", tenant_id),
        parse=one(Tenant),
        describe="getting tenant",
        context={"tenant_id": tenant_id},
    )


def _get_metrics_integration(tenant_id: str) -> Call[MetricsIntegration]:
    tenant_id = validate.tenant_id(tenant_id)
    return Call(
        method="GET",
        path=build_path("tenants", tenant_id, "metrics-integration"),
        parse=one(MetricsIntegration),
        describe="getting tenant metrics integration",
        context={"tenant_id": tenant_id},
    )


# --- Services ---


class TenantService(Service):
    """Tenants (shown as projects in the Aura Console).

    Each method lists the errors specific to it. The errors any call can raise are listed on
    :class:`~aura_python_sdk.AuraClient`.
    """

    def list(self) -> builtins.list[TenantSummary]:
        """Every tenant the credentials can access."""
        return self._run(_list())

    def get(self, tenant_id: str) -> Tenant:
        """A tenant and the instance configurations it can create.

        Raises:
            AuraValidationError: ``tenant_id`` is invalid; nothing was sent.
            NotFoundError: The tenant doesn't exist.
        """
        return self._run(_get(tenant_id))

    def get_metrics_integration(self, tenant_id: str) -> MetricsIntegration:
        """The project-level Prometheus metrics endpoint (Go: ``GetMetrics``).

        Raises:
            AuraValidationError: ``tenant_id`` is invalid; nothing was sent.
            NotFoundError: The tenant doesn't exist.
        """
        return self._run(_get_metrics_integration(tenant_id))


class AsyncTenantService(AsyncService):
    """Async version of :class:`TenantService`."""

    async def list(self) -> builtins.list[TenantSummary]:
        """Every tenant the credentials can access."""
        return await self._run(_list())

    async def get(self, tenant_id: str) -> Tenant:
        """A tenant and the instance configurations it can create."""
        return await self._run(_get(tenant_id))

    async def get_metrics_integration(self, tenant_id: str) -> MetricsIntegration:
        """The project-level Prometheus metrics endpoint (Go: ``GetMetrics``)."""
        return await self._run(_get_metrics_integration(tenant_id))
