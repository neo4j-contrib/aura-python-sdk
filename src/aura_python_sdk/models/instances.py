"""Instance models (Go: instances.go)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from aura_python_sdk.models._common import CloudProvider, InstanceType


class InstanceStatus(StrEnum):
    """Lifecycle states of an instance."""

    CREATING = "creating"
    DESTROYING = "destroying"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    SUSPENDING = "suspending"
    SUSPENDED = "suspended"
    RESUMING = "resuming"
    LOADING = "loading"
    LOADING_FAILED = "loading failed"
    RESTORING = "restoring"
    UPDATING = "updating"
    OVERWRITING = "overwriting"
    # Not in the v1 spec's enum, but defined by the Go SDK.
    STOPPED = "stopped"
    AVAILABLE = "available"


class CDCEnrichmentMode(StrEnum):
    OFF = "OFF"
    DIFF = "DIFF"
    FULL = "FULL"


@dataclass(frozen=True, slots=True, kw_only=True)
class InstanceSummary:
    """An instance as returned by ``GET /instances``."""

    id: str
    name: str
    tenant_id: str
    cloud_provider: CloudProvider | str
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Instance:
    """Full details of an instance.

    ``connection_url`` can be ``None`` (the live API sends null for some instances).
    ``storage`` is not returned for AuraDB Free. ``graph_nodes`` and ``graph_relationships`` are
    returned only for Free instances. ``secondaries_count`` is returned only for Virtual
    Dedicated Cloud, and ``cdc_enrichment_mode`` only for Virtual Dedicated Cloud and Business
    Critical.
    """

    id: str
    name: str
    status: InstanceStatus | str
    tenant_id: str
    cloud_provider: CloudProvider | str
    # Required by the spec, but the live API returns null for some instances.
    connection_url: str | None = None
    region: str
    type: InstanceType | str
    memory: str
    storage: str | None = None
    created_at: datetime | None = None
    metrics_integration_url: str | None = None
    customer_managed_key_id: str | None = None
    graph_nodes: int | None = None
    graph_relationships: int | None = None
    secondaries_count: int | None = None
    cdc_enrichment_mode: CDCEnrichmentMode | str | None = None
    vector_optimized: bool | None = None
    graph_analytics_plugin: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatedInstance:
    """Returned when an instance is created, including its initial credentials.

    ``password`` is shown only once and is left out of ``repr()``. Store it securely.
    """

    id: str
    name: str
    tenant_id: str
    cloud_provider: CloudProvider | str
    region: str
    type: InstanceType | str
    connection_url: str
    username: str
    password: str = field(repr=False)
    created_at: datetime | None = None
    vector_optimized: bool | None = None
    graph_analytics_plugin: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class InstanceConfig:
    """Settings for a new instance (Go: ``CreateInstanceConfigData``).

    Valid combinations of cloud provider, region, type, version and memory for a tenant come from
    ``client.tenants.get(tenant_id).instance_configurations``.
    """

    name: str
    tenant_id: str
    cloud_provider: CloudProvider | str
    region: str
    type: InstanceType | str
    version: str
    memory: str
    vector_optimized: bool | None = None
    graph_analytics_plugin: bool | None = None
    customer_managed_key_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class InstanceSizeEstimate:
    """Result of ``POST /instances/sizing``."""

    recommended_size: str
    min_required_memory: str
    did_exceed_maximum: bool
