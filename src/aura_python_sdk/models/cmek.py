"""Customer-managed encryption key models (Go: cmek.go)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aura_python_sdk.models._common import CloudProvider, InstanceType


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerManagedKeySummary:
    """A key as returned by ``GET /customer-managed-keys``."""

    id: str
    name: str
    tenant_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerManagedKey:
    """Full details of a customer-managed key.

    ``key_id`` is the key's ID in your cloud provider (the key ARN on AWS). The key can only encrypt
    instances of ``instance_type`` in ``region``.
    """

    id: str
    name: str
    tenant_id: str
    cloud_provider: CloudProvider | str
    region: str
    instance_type: InstanceType | str
    key_id: str
    status: str
    created: datetime | None = None
