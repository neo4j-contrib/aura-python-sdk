"""Snapshot models (Go: snapshots.go)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SnapshotStatus(StrEnum):
    COMPLETED = "Completed"
    IN_PROGRESS = "InProgress"
    FAILED = "Failed"
    PENDING = "Pending"
    CANCELLED = "Cancelled"


class SnapshotProfile(StrEnum):
    AD_HOC = "AdHoc"
    SCHEDULED = "Scheduled"


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot:
    """A snapshot of an instance.

    Only snapshots with ``exportable`` set can be used to create a new instance.
    """

    snapshot_id: str
    instance_id: str
    status: SnapshotStatus | str
    profile: SnapshotProfile | str | None = None
    timestamp: datetime | None = None
    exportable: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatedSnapshot:
    """Returned when an on-demand snapshot is started."""

    snapshot_id: str
