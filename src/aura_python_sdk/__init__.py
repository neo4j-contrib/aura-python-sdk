"""Python client library for the Neo4j Aura API (v1).

Example::

    import aura_python_sdk as aura

    with aura.AuraClient(client_id="...", client_secret="...") as client:
        for instance in client.instances.list():
            print(instance.id, instance.name)

For asyncio, use :class:`AsyncAuraClient`, which has the same services with awaitable methods.
"""

import logging

from aura_python_sdk._client import AsyncAuraClient, AuraClient
from aura_python_sdk._errors import (
    AuraAPIError,
    AuraClientClosedError,
    AuraConfigurationError,
    AuraConnectionError,
    AuraError,
    AuraResponseError,
    AuraTimeoutError,
    AuraValidationError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ErrorDetail,
    MetricNotFoundError,
    NotFoundError,
    OperationFailedError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    WaitTimeoutError,
)
from aura_python_sdk._transport import AsyncHttpTransport, HttpRequest, HttpResponse, HttpTransport
from aura_python_sdk._version import __version__
from aura_python_sdk.models import (
    CDCEnrichmentMode,
    CloudProvider,
    ConnectionMetrics,
    CreatedInstance,
    CreatedSnapshot,
    CustomerManagedKey,
    CustomerManagedKeySummary,
    DeletedGDSSession,
    GDSSession,
    GDSSessionConfig,
    GDSSessionSizeEstimate,
    GDSSessionStatus,
    HealthStatus,
    Instance,
    InstanceConfig,
    InstanceConfiguration,
    InstanceHealth,
    InstanceSizeEstimate,
    InstanceStatus,
    InstanceSummary,
    InstanceType,
    MetricsIntegration,
    PrometheusMetric,
    PrometheusMetrics,
    QueryMetrics,
    ResourceMetrics,
    Snapshot,
    SnapshotProfile,
    SnapshotStatus,
    StorageMetrics,
    Tenant,
    TenantSummary,
)

# Library convention: emit nothing unless the application configures logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AsyncAuraClient",
    "AsyncHttpTransport",
    "AuraAPIError",
    "AuraClient",
    "AuraClientClosedError",
    "AuraConfigurationError",
    "AuraConnectionError",
    "AuraError",
    "AuraResponseError",
    "AuraTimeoutError",
    "AuraValidationError",
    "AuthenticationError",
    "BadRequestError",
    "CDCEnrichmentMode",
    "CloudProvider",
    "ConflictError",
    "ConnectionMetrics",
    "CreatedInstance",
    "CreatedSnapshot",
    "CustomerManagedKey",
    "CustomerManagedKeySummary",
    "DeletedGDSSession",
    "ErrorDetail",
    "GDSSession",
    "GDSSessionConfig",
    "GDSSessionSizeEstimate",
    "GDSSessionStatus",
    "HealthStatus",
    "HttpRequest",
    "HttpResponse",
    "HttpTransport",
    "Instance",
    "InstanceConfig",
    "InstanceConfiguration",
    "InstanceHealth",
    "InstanceSizeEstimate",
    "InstanceStatus",
    "InstanceSummary",
    "InstanceType",
    "MetricNotFoundError",
    "MetricsIntegration",
    "NotFoundError",
    "OperationFailedError",
    "PermissionDeniedError",
    "PrometheusMetric",
    "PrometheusMetrics",
    "QueryMetrics",
    "RateLimitError",
    "ResourceMetrics",
    "ServerError",
    "Snapshot",
    "SnapshotProfile",
    "SnapshotStatus",
    "StorageMetrics",
    "Tenant",
    "TenantSummary",
    "WaitTimeoutError",
    "__version__",
]
