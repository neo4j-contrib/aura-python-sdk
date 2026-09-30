"""The wait_* helpers: instances.wait_for_status, snapshots.wait_for_completion and
graph_analytics.wait_until_ready."""

from __future__ import annotations

import pickle
from typing import Any

import pytest

import aura_python_sdk as aura
from tests.fakes import FakeAsyncSleep, FakeAsyncTransport, FakeClock, json_response, token_response
from tests.unit.conftest import INSTANCE, INSTANCE_ID, SESSION, SNAPSHOT_ID, Api

SNAPSHOT = {"instance_id": INSTANCE_ID, "snapshot_id": SNAPSHOT_ID, "status": "Completed"}


def _data(resource: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {"data": {**resource, **changes}}


@pytest.fixture
def clock(api: Api) -> FakeClock:
    clock = FakeClock()
    for service in (api.client.instances, api.client.snapshots, api.client.graph_analytics):
        service._clock = clock
        service._sleep = clock.sleep
    return clock


def test_wait_for_status_polls_until_running(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(INSTANCE, status="creating"))
    api.reply(200, _data(INSTANCE, status="creating"))
    api.reply(200, _data(INSTANCE, status="running"))

    instance = api.client.instances.wait_for_status(INSTANCE_ID, interval=5)

    assert instance.status == aura.InstanceStatus.RUNNING
    assert clock.sleeps == [5.0, 5.0]
    assert len(api.transport.api_requests) == 3


def test_wait_for_status_returns_at_once_when_already_there(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(INSTANCE, status="paused"))
    instance = api.client.instances.wait_for_status(INSTANCE_ID, status="paused")
    assert instance.status == aura.InstanceStatus.PAUSED
    assert clock.sleeps == []


def test_wait_for_status_raises_on_loading_failed(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(INSTANCE, status="loading"))
    api.reply(200, _data(INSTANCE, status="loading failed"))

    with pytest.raises(aura.OperationFailedError, match="loading failed") as info:
        api.client.instances.wait_for_status(INSTANCE_ID)

    assert isinstance(info.value.resource, aura.Instance)
    assert info.value.resource.status == aura.InstanceStatus.LOADING_FAILED


def test_wait_for_status_can_wait_for_loading_failed(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(INSTANCE, status="loading failed"))
    instance = api.client.instances.wait_for_status(
        INSTANCE_ID, status=aura.InstanceStatus.LOADING_FAILED
    )
    assert instance.status == aura.InstanceStatus.LOADING_FAILED


def test_wait_times_out_with_the_last_state(api: Api, clock: FakeClock) -> None:
    for _ in range(4):
        api.reply(200, _data(INSTANCE, status="creating"))

    with pytest.raises(aura.WaitTimeoutError, match="status is creating") as info:
        api.client.instances.wait_for_status(INSTANCE_ID, timeout=25, interval=10)

    # Polls at 0, 10 and 20 s, then sleeps only the 5 s left before the final check.
    assert clock.sleeps == [10.0, 10.0, 5.0]
    assert isinstance(info.value.resource, aura.Instance)
    assert info.value.resource.status == "creating"
    assert isinstance(info.value, TimeoutError)


NOT_FOUND = {"errors": [{"message": "Instance not found"}]}


def test_not_found_in_the_first_minute_is_retried(api: Api, clock: FakeClock) -> None:
    # A new instance can take a moment to appear in the API after create().
    api.reply(404, NOT_FOUND)
    api.reply(404, NOT_FOUND)
    api.reply(200, _data(INSTANCE, status="creating"))
    api.reply(200, _data(INSTANCE, status="running"))

    instance = api.client.instances.wait_for_status(INSTANCE_ID, interval=20)

    assert instance.status == aura.InstanceStatus.RUNNING
    assert clock.sleeps == [20.0, 20.0, 20.0]


def test_not_found_after_the_first_minute_is_raised(api: Api, clock: FakeClock) -> None:
    for _ in range(4):
        api.reply(404, NOT_FOUND)
    with pytest.raises(aura.NotFoundError):
        api.client.instances.wait_for_status(INSTANCE_ID, interval=25)
    # 404s at 0, 25 and 50 s are retried; the one at 75 s is raised.
    assert clock.sleeps == [25.0, 25.0, 25.0]


def test_timeout_while_not_found_reports_it(api: Api, clock: FakeClock) -> None:
    api.reply(404, NOT_FOUND)
    api.reply(404, NOT_FOUND)
    with pytest.raises(aura.WaitTimeoutError, match="not found") as info:
        api.client.instances.wait_for_status(INSTANCE_ID, timeout=10, interval=10)
    assert info.value.resource is None


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.wait_for_status("bad"),
        lambda s: s.wait_for_status(INSTANCE_ID, status=""),
        lambda s: s.wait_for_status(INSTANCE_ID, timeout=0),
        lambda s: s.wait_for_status(INSTANCE_ID, interval=-1),
        lambda s: s.wait_for_status(INSTANCE_ID, timeout=float("inf")),
    ],
)
def test_wait_for_status_validates_before_polling(api: Api, clock: FakeClock, call: Any) -> None:
    with pytest.raises(aura.AuraValidationError):
        call(api.client.instances)
    api.assert_no_request()


def test_wait_for_completion(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(SNAPSHOT, status="Pending"))
    api.reply(200, _data(SNAPSHOT, status="InProgress"))
    api.reply(200, _data(SNAPSHOT, status="Completed"))

    snapshot = api.client.snapshots.wait_for_completion(INSTANCE_ID, SNAPSHOT_ID)

    assert snapshot.status == aura.SnapshotStatus.COMPLETED
    assert clock.sleeps == [10.0, 10.0]


@pytest.mark.parametrize("status", ["Failed", "Cancelled"])
def test_wait_for_completion_raises_on_failure(api: Api, clock: FakeClock, status: str) -> None:
    api.reply(200, _data(SNAPSHOT, status=status))
    with pytest.raises(aura.OperationFailedError, match=status):
        api.client.snapshots.wait_for_completion(INSTANCE_ID, SNAPSHOT_ID)


def test_wait_until_ready(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(SESSION, status="Creating"))
    api.reply(200, _data(SESSION, status="Ready"))

    session = api.client.graph_analytics.wait_until_ready(SESSION["id"])

    assert session.status == aura.GDSSessionStatus.READY
    assert clock.sleeps == [10.0]


@pytest.mark.parametrize("status", ["Failed", "Expired"])
def test_wait_until_ready_raises_on_failure(api: Api, clock: FakeClock, status: str) -> None:
    api.reply(200, _data(SESSION, status=status))
    with pytest.raises(aura.OperationFailedError, match=status):
        api.client.graph_analytics.wait_until_ready(SESSION["id"])


def test_wait_errors_pickle_with_their_resource(api: Api, clock: FakeClock) -> None:
    api.reply(200, _data(INSTANCE, status="loading failed"))
    with pytest.raises(aura.OperationFailedError) as info:
        api.client.instances.wait_for_status(INSTANCE_ID)
    copy = pickle.loads(pickle.dumps(info.value))  # noqa: S301 - round-tripping our own object
    assert copy.resource == info.value.resource


@pytest.mark.anyio
async def test_async_wait_for_status() -> None:
    clock = FakeClock()
    transport = FakeAsyncTransport(
        [
            token_response(),
            json_response(200, _data(INSTANCE, status="resuming")),
            json_response(200, _data(INSTANCE, status="running")),
        ]
    )
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    client.instances._clock = clock
    client.instances._sleep = FakeAsyncSleep(clock)

    instance = await client.instances.wait_for_status(INSTANCE_ID, interval=3)

    assert instance.status == aura.InstanceStatus.RUNNING
    assert clock.sleeps == [3.0]


@pytest.mark.anyio
async def test_async_wait_times_out() -> None:
    clock = FakeClock()
    transport = FakeAsyncTransport(
        [token_response(), *[json_response(200, _data(SNAPSHOT, status="Pending"))] * 2]
    )
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    client.snapshots._clock = clock
    client.snapshots._sleep = FakeAsyncSleep(clock)

    with pytest.raises(aura.WaitTimeoutError):
        await client.snapshots.wait_for_completion(
            INSTANCE_ID, SNAPSHOT_ID, timeout=10, interval=10
        )
    assert clock.sleeps == [10.0]
