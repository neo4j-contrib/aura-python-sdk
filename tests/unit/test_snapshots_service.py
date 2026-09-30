import datetime as dt
from typing import Any

import pytest

from aura_python_sdk import AuraValidationError, InstanceStatus, SnapshotProfile, SnapshotStatus
from tests.unit.conftest import BASE, INSTANCE, INSTANCE_ID, SNAPSHOT_ID, Api

SNAPSHOT = {
    "instance_id": INSTANCE_ID,
    "snapshot_id": SNAPSHOT_ID,
    "profile": "AdHoc",
    "status": "Completed",
    "timestamp": "2023-01-20T13:44:42Z",
    "exportable": True,
}


def test_list(api: Api) -> None:
    api.reply(200, {"data": [SNAPSHOT]})
    [snapshot] = api.client.snapshots.list(INSTANCE_ID)
    assert snapshot.status is SnapshotStatus.COMPLETED
    assert snapshot.profile is SnapshotProfile.AD_HOC
    assert api.request.url == f"{BASE}/instances/{INSTANCE_ID}/snapshots"


def test_list_with_date(api: Api) -> None:
    api.reply(200, {"data": []})
    assert api.client.snapshots.list(INSTANCE_ID, date=dt.date(2024, 3, 7)) == []
    assert api.request.url == f"{BASE}/instances/{INSTANCE_ID}/snapshots?date=2024-03-07"


@pytest.mark.parametrize("value", ["2024-03-07", dt.datetime(2024, 3, 7, tzinfo=dt.UTC)])
def test_list_rejects_non_date(api: Api, value: object) -> None:
    with pytest.raises(AuraValidationError, match=r"datetime\.date"):
        api.client.snapshots.list(INSTANCE_ID, date=value)  # type: ignore[arg-type]
    api.assert_no_request()


def test_get(api: Api) -> None:
    api.reply(200, {"data": SNAPSHOT})
    snapshot = api.client.snapshots.get(INSTANCE_ID, SNAPSHOT_ID)
    assert snapshot.snapshot_id == SNAPSHOT_ID
    assert snapshot.timestamp == dt.datetime(2023, 1, 20, 13, 44, 42, tzinfo=dt.UTC)
    assert api.request.url == f"{BASE}/instances/{INSTANCE_ID}/snapshots/{SNAPSHOT_ID}"


def test_create(api: Api) -> None:
    api.reply(202, {"data": {"snapshot_id": SNAPSHOT_ID}})
    created = api.client.snapshots.create(INSTANCE_ID)
    assert created.snapshot_id == SNAPSHOT_ID
    assert (api.request.method, api.request.url) == (
        "POST",
        f"{BASE}/instances/{INSTANCE_ID}/snapshots",
    )
    assert api.request.body is None


def test_restore(api: Api) -> None:
    api.reply(202, {"data": {**INSTANCE, "status": "restoring"}})
    instance = api.client.snapshots.restore(INSTANCE_ID, SNAPSHOT_ID)
    assert instance.status is InstanceStatus.RESTORING
    assert (api.request.method, api.request.url) == (
        "POST",
        f"{BASE}/instances/{INSTANCE_ID}/snapshots/{SNAPSHOT_ID}/restore",
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.list("bad"),
        lambda s: s.get("bad", SNAPSHOT_ID),
        lambda s: s.get(INSTANCE_ID, "bad"),
        lambda s: s.create(""),
        lambda s: s.restore(INSTANCE_ID, "2023-01-20T13:44:42Z"),
    ],
)
def test_invalid_ids_send_nothing(api: Api, call: Any) -> None:
    with pytest.raises(AuraValidationError):
        call(api.client.snapshots)
    api.assert_no_request()
