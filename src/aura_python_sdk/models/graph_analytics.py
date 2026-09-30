"""Graph Analytics (GDS) session models (Go: graphanalytics.go)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from aura_python_sdk.models._common import CloudProvider


class GDSSessionStatus(StrEnum):
    """Lifecycle states of a Graph Analytics session."""

    CREATING = "Creating"
    READY = "Ready"
    EXPIRED = "Expired"
    FAILED = "Failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class GDSSession:
    """A Graph Analytics session.

    ``instance_id`` and ``database_uuid`` are empty for a standalone session. ``ttl`` is a
    duration string such as ``"20m0s"``.
    """

    id: str
    name: str
    memory: str
    host: str
    tenant_id: str
    user_id: str
    status: GDSSessionStatus | str | None = None
    instance_id: str | None = None
    database_uuid: str | None = None
    cloud_provider: CloudProvider | str | None = None
    region: str | None = None
    created_at: datetime | None = None
    expiry_date: datetime | None = None
    ttl: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GDSSessionConfig:
    """Settings for a new session (Go: ``CreateGDSSessionConfigData``).

    Set ``instance_id`` and ``database_uuid`` to attach the session to an AuraDB instance, or
    ``cloud_provider`` and ``region`` for a standalone session. ``ttl`` is a duration string
    such as ``"1h"``.
    """

    name: str
    memory: str
    tenant_id: str | None = None
    ttl: str | None = None
    instance_id: str | None = None
    database_uuid: str | None = None
    cloud_provider: CloudProvider | str | None = None
    region: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GDSSessionSizeEstimate:
    """Result of ``POST /graph-analytics/sessions/sizing``."""

    estimated_memory: str
    recommended_size: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DeletedGDSSession:
    """Returned when a session is deleted."""

    id: str
