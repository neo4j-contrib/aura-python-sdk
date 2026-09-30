"""``client.snapshots`` (Go: SnapshotService)."""

from __future__ import annotations

import builtins
import datetime as dt

from aura_python_sdk import _validation as validate
from aura_python_sdk._errors import AuraValidationError
from aura_python_sdk._internal._call import Call, many, one
from aura_python_sdk._internal._request import build_path
from aura_python_sdk.models.instances import Instance
from aura_python_sdk.models.snapshots import CreatedSnapshot, Snapshot
from aura_python_sdk.services._base import AsyncService, Service

# --- Operations (validation, request and parsing; no I/O) ---


def _list(instance_id: str, date: dt.date | None) -> Call[list[Snapshot]]:
    instance_id = validate.instance_id(instance_id)
    if date is not None and (not isinstance(date, dt.date) or isinstance(date, dt.datetime)):
        raise AuraValidationError("date must be a datetime.date")
    return Call(
        method="GET",
        path=build_path("instances", instance_id, "snapshots"),
        params={"date": date.isoformat() if date else None},
        parse=many(Snapshot),
        describe="listing snapshots",
        context={"instance_id": instance_id},
    )


def _get(instance_id: str, snapshot_id: str) -> Call[Snapshot]:
    instance_id = validate.instance_id(instance_id)
    snapshot_id = validate.snapshot_id(snapshot_id)
    return Call(
        method="GET",
        path=build_path("instances", instance_id, "snapshots", snapshot_id),
        parse=one(Snapshot),
        describe="getting snapshot",
        context={"instance_id": instance_id, "snapshot_id": snapshot_id},
    )


def _create(instance_id: str) -> Call[CreatedSnapshot]:
    instance_id = validate.instance_id(instance_id)
    return Call(
        method="POST",
        path=build_path("instances", instance_id, "snapshots"),
        parse=one(CreatedSnapshot),
        describe="creating snapshot",
        done="snapshot started",
        context={"instance_id": instance_id},
    )


def _restore(instance_id: str, snapshot_id: str) -> Call[Instance]:
    instance_id = validate.instance_id(instance_id)
    snapshot_id = validate.snapshot_id(snapshot_id)
    return Call(
        method="POST",
        path=build_path("instances", instance_id, "snapshots", snapshot_id, "restore"),
        parse=one(Instance),
        describe="restoring snapshot",
        done="snapshot restore started",
        context={"instance_id": instance_id, "snapshot_id": snapshot_id},
    )


# --- Services ---


class SnapshotService(Service):
    """Instance snapshots."""

    def list(self, instance_id: str, date: dt.date | None = None) -> builtins.list[Snapshot]:
        """Snapshots of an instance taken on ``date``. The API defaults to today."""
        return self._run(_list(instance_id, date))

    def get(self, instance_id: str, snapshot_id: str) -> Snapshot:
        """Details of one snapshot."""
        return self._run(_get(instance_id, snapshot_id))

    def create(self, instance_id: str) -> CreatedSnapshot:
        """Start an on-demand snapshot."""
        return self._run(_create(instance_id))

    def restore(self, instance_id: str, snapshot_id: str) -> Instance:
        """Restore an instance from one of its own snapshots, replacing its current data."""
        return self._run(_restore(instance_id, snapshot_id))


class AsyncSnapshotService(AsyncService):
    """Async version of :class:`SnapshotService`, with the same arguments and behaviour."""

    async def list(self, instance_id: str, date: dt.date | None = None) -> builtins.list[Snapshot]:
        """See :meth:`SnapshotService.list`."""
        return await self._run(_list(instance_id, date))

    async def get(self, instance_id: str, snapshot_id: str) -> Snapshot:
        """See :meth:`SnapshotService.get`."""
        return await self._run(_get(instance_id, snapshot_id))

    async def create(self, instance_id: str) -> CreatedSnapshot:
        """See :meth:`SnapshotService.create`."""
        return await self._run(_create(instance_id))

    async def restore(self, instance_id: str, snapshot_id: str) -> Instance:
        """See :meth:`SnapshotService.restore`."""
        return await self._run(_restore(instance_id, snapshot_id))
