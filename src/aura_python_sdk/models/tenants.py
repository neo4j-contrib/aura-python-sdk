"""Tenant (project) models (Go: tenants.go)."""

from __future__ import annotations

from dataclasses import dataclass

from aura_python_sdk.models._common import CloudProvider, InstanceType


@dataclass(frozen=True, slots=True, kw_only=True)
class TenantSummary:
    """A tenant as returned by ``GET /tenants``."""

    id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class InstanceConfiguration:
    """An instance configuration the tenant is allowed to create."""

    cloud_provider: CloudProvider | str
    region: str
    region_name: str
    type: InstanceType | str
    memory: str
    version: str
    storage: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Tenant:
    """A tenant and the instance configurations available to it (``GET /tenants/{id}``)."""

    id: str
    name: str
    instance_configurations: tuple[InstanceConfiguration, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricsIntegration:
    """The project-level Prometheus metrics endpoint."""

    endpoint: str
