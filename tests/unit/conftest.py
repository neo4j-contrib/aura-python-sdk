from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from aura_python_sdk import AuraClient, HttpRequest
from tests.fakes import FakeTransport, json_response, token_response

TENANT_ID = "6981ace7-efe8-4f5c-b7c5-267b5162ce91"
INSTANCE_ID = "2f49c2b3"
OTHER_INSTANCE_ID = "b51dc964"
SNAPSHOT_ID = "e9ac0fa5-e1f9-4bb2-b0a2-5d4e5b3d8b43"
BASE = "https://api.neo4j.io/v1"

INSTANCE = {
    "id": INSTANCE_ID,
    "name": "Production",
    "status": "running",
    "tenant_id": TENANT_ID,
    "cloud_provider": "gcp",
    "connection_url": "neo4j+s://2f49c2b3.databases.neo4j.io",
    "region": "europe-west1",
    "type": "enterprise-db",
    "memory": "8GB",
    "storage": "16GB",
    "created_at": "2023-01-20T13:44:42Z",
}

SESSION = {
    "id": "s-04de43fe-67ab-4",
    "name": "people-and-fruit",
    "memory": "8GB",
    "host": "s-04de43fe-67ab-4-gds.example.neo4j.io",
    "tenant_id": TENANT_ID,
    "user_id": "user-1",
    "status": "Ready",
    "ttl": "20m0s",
}


@dataclass
class Api:
    """An AuraClient wired to a FakeTransport that already holds a token response."""

    client: AuraClient
    transport: FakeTransport

    def reply(self, status: int, payload: object) -> None:
        self.transport.queue(json_response(status, payload))

    @property
    def request(self) -> HttpRequest:
        """The single API request sent (excluding the token request)."""
        requests = self.transport.api_requests
        assert len(requests) == 1, f"expected one API request, got {len(requests)}"
        return requests[0]

    @property
    def body(self) -> Any:
        body = self.request.body
        return None if body is None else json.loads(body)

    def assert_no_request(self) -> None:
        assert self.transport.requests == []


@pytest.fixture
def api() -> Api:
    transport = FakeTransport([token_response()])
    client = AuraClient(client_id="id", client_secret="secret", transport=transport)
    return Api(client, transport)
