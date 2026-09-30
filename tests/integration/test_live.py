"""Live tests against the real Aura API.

Skipped unless AURA_CLIENT_ID and AURA_CLIENT_SECRET are set. Run them with:

    uv run pytest -m integration

The tests only read unless AURA_INTEGRATION_WRITE=1 and AURA_TENANT_ID are also set. Then
test_create_pause_resume_delete creates the smallest AuraDB Professional instance, pauses and
resumes it, and deletes it. That runs for a few minutes and is billed.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator

import pytest

import aura_python_sdk as aura

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("AURA_CLIENT_ID") and os.environ.get("AURA_CLIENT_SECRET")),
        reason="AURA_CLIENT_ID and AURA_CLIENT_SECRET are not set",
    ),
]

WRITES_ENABLED = os.environ.get("AURA_INTEGRATION_WRITE") == "1"
TENANT_ID = os.environ.get("AURA_TENANT_ID", "")


@pytest.fixture(scope="module")
def client() -> Iterator[aura.AuraClient]:
    with aura.AuraClient.from_env(timeout=60) as live_client:
        yield live_client


def test_tenants(client: aura.AuraClient) -> None:
    tenants = client.tenants.list()
    assert tenants, "the credentials should see at least one tenant"
    tenant = client.tenants.get(tenants[0].id)
    assert tenant.id == tenants[0].id


def test_instances_list_and_get(client: aura.AuraClient) -> None:
    instances = client.instances.list()
    for summary in instances[:3]:
        instance = client.instances.get(summary.id)
        assert instance.id == summary.id
        assert instance.tenant_id == summary.tenant_id


def test_instances_list_filtered_by_tenant(client: aura.AuraClient) -> None:
    tenant_id = client.tenants.list()[0].id
    assert all(i.tenant_id == tenant_id for i in client.instances.list(tenant_id=tenant_id))


def test_snapshots_for_first_instance(client: aura.AuraClient) -> None:
    instances = client.instances.list()
    if not instances:
        pytest.skip("no instances to list snapshots for")
    for snapshot in client.snapshots.list(instances[0].id):
        assert snapshot.instance_id == instances[0].id


def _skip_if_forbidden(call: Callable[[], object]) -> object:
    """Run ``call``, but skip the test if these credentials lack permission for it."""
    try:
        return call()
    except aura.PermissionDeniedError as err:
        pytest.skip(f"credentials lack permission: {err.message}")


def test_cmek_list(client: aura.AuraClient) -> None:
    assert isinstance(_skip_if_forbidden(client.cmek.list), list)


def test_sessions_list(client: aura.AuraClient) -> None:
    assert isinstance(_skip_if_forbidden(client.graph_analytics.list), list)


def test_unknown_instance_is_not_found(client: aura.AuraClient) -> None:
    with pytest.raises(aura.NotFoundError):
        client.instances.get("00000000")


def test_bad_credentials_are_rejected() -> None:
    with (
        aura.AuraClient(client_id="not-real", client_secret="not-real") as bad,
        pytest.raises(aura.AuthenticationError),
    ):
        bad.tenants.list()


def _smallest_pro_config(client: aura.AuraClient) -> aura.InstanceConfig:
    """The cheapest AuraDB Professional configuration the tenant offers, preferring GCP."""
    offered = [
        c
        for c in client.tenants.get(TENANT_ID).instance_configurations
        if c.type == aura.InstanceType.PROFESSIONAL_DB
    ]
    if not offered:
        pytest.skip("the tenant can't create AuraDB Professional instances")

    def cost(c: aura.InstanceConfiguration) -> tuple[float, bool, bool]:
        memory_gb = float(c.memory.removesuffix("GB"))  # the API offers sizes like "1GB"
        return (memory_gb, c.cloud_provider != "gcp", c.region != "europe-west1")

    chosen = min(offered, key=cost)
    return aura.InstanceConfig(
        name="aura-python-sdk-it",
        tenant_id=TENANT_ID,
        cloud_provider=chosen.cloud_provider,
        region=chosen.region,
        type=aura.InstanceType.PROFESSIONAL_DB,
        version=chosen.version,
        memory=chosen.memory,
    )


@pytest.mark.skipif(
    not (WRITES_ENABLED and TENANT_ID), reason="needs AURA_INTEGRATION_WRITE=1 and AURA_TENANT_ID"
)
def test_create_pause_resume_delete(client: aura.AuraClient) -> None:
    # Uses the smallest AuraDB Professional instance: the free tier can't be paused. It runs for
    # a few minutes, so the cost is small.
    created = client.instances.create(_smallest_pro_config(client))
    deleted = False
    try:
        # Exercises the wait helper, including its tolerance of a new instance's early 404s.
        running = client.instances.wait_for_status(created.id)
        assert running.connection_url
        client.instances.pause(created.id)
        client.instances.wait_for_status(created.id, status=aura.InstanceStatus.PAUSED)
        client.instances.resume(created.id)
        client.instances.wait_for_status(created.id, status=aura.InstanceStatus.RUNNING)
        client.instances.delete(created.id)
        deleted = True
        # While it is torn down the API may leave fields such as memory out; get() must still
        # parse it (or report it gone).
        with contextlib.suppress(aura.NotFoundError):
            client.instances.get(created.id)
    finally:
        if not deleted:
            client.instances.delete(created.id)


@pytest.mark.anyio
async def test_async_client_reads_the_same_data(client: aura.AuraClient) -> None:
    async with aura.AsyncAuraClient.from_env(timeout=60) as async_client:
        async_tenants = await async_client.tenants.list()
    assert {t.id for t in async_tenants} == {t.id for t in client.tenants.list()}
