"""AsyncAuraClient end-to-end over real sockets and the real async httpx transport."""

import asyncio
import time

import pytest

import aura_python_sdk as aura
from tests.blackbox.conftest import FakeAura, Reply
from tests.blackbox.test_blackbox import INSTANCE, TENANT_ID

pytestmark = pytest.mark.anyio


async def test_concurrent_gets_share_one_token(fake_aura: FakeAura) -> None:
    fake_aura.route("GET", "/v1/instances/2f49c2b3", Reply.json(200, {"data": INSTANCE}))
    async with fake_aura.async_client() as client:
        results = await asyncio.gather(*(client.instances.get("2f49c2b3") for _ in range(5)))
    assert {r.id for r in results} == {"2f49c2b3"}
    assert [r.path for r in fake_aura.received].count("/oauth/token") == 1
    assert len(fake_aura.api_requests()) == 5


async def test_list_with_filter_and_headers(fake_aura: FakeAura) -> None:
    fake_aura.route("GET", "/v1/instances", Reply.json(200, {"data": []}))
    async with fake_aura.async_client(user_agent="my-app/1") as client:
        assert await client.instances.list(tenant_id=TENANT_ID) == []
    [request] = fake_aura.api_requests()
    assert request.query == f"tenantId={TENANT_ID}"
    assert request.headers["user-agent"] == "my-app/1"
    assert request.headers["authorization"] == "Bearer local-token"


async def test_api_error_is_mapped(fake_aura: FakeAura) -> None:
    fake_aura.route(
        "POST",
        "/v1/instances/2f49c2b3/pause",
        Reply.json(409, {"errors": [{"message": "Instance is not running"}]}),
    )
    async with fake_aura.async_client() as client:
        with pytest.raises(aura.ConflictError, match="Instance is not running"):
            await client.instances.pause("2f49c2b3")


async def test_slow_post_times_out_and_is_not_retried(fake_aura: FakeAura) -> None:
    fake_aura.route("POST", "/v1/instances/2f49c2b3/pause", Reply(202, b"{}", delay=2.0))
    started = time.monotonic()
    async with fake_aura.async_client(timeout=0.5, max_retries=3) as client:
        with pytest.raises(aura.AuraTimeoutError):
            await client.instances.pause("2f49c2b3")
    assert time.monotonic() - started < 1.9
    assert len(fake_aura.api_requests()) == 1


async def test_delete_with_no_content(fake_aura: FakeAura) -> None:
    fake_aura.route("DELETE", "/v1/customer-managed-keys/key-1", Reply(204))
    async with fake_aura.async_client() as client:
        await client.cmek.delete("key-1")
