"""A local Aura API stand-in (Go: client_blackbox_test.go's httptest.Server).

These tests use only the public API and the real httpx transport, over real sockets on
127.0.0.1. Nothing reaches the internet.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import pytest

import aura_python_sdk as aura


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0

    @classmethod
    def json(cls, status: int, payload: object, **headers: str) -> Reply:
        return cls(
            status, json.dumps(payload).encode(), {"Content-Type": "application/json", **headers}
        )


@dataclass
class Received:
    method: str
    path: str
    query: str
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


Route = Callable[[Received], Reply] | Reply


class FakeAura:
    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Route] = {
            ("POST", "/oauth/token"): Reply.json(
                200, {"token_type": "Bearer", "access_token": "local-token", "expires_in": 3600}
            )
        }
        self.received: list[Received] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        # Don't wait for slow handlers (e.g. the timeout test) when shutting down.
        self._server.daemon_threads = True
        self._server.block_on_close = False
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def route(self, method: str, path: str, reply: Route) -> None:
        self.routes[(method, path)] = reply

    def api_requests(self) -> list[Received]:
        return [r for r in self.received if r.path != "/oauth/token"]

    def client(self, **options: Any) -> aura.AuraClient:
        options.setdefault("timeout", 5)
        return aura.AuraClient(
            client_id="local-id",
            client_secret="local-secret",
            base_url=self.url,
            allow_insecure_base_url=True,
            **options,
        )

    def async_client(self, **options: Any) -> aura.AsyncAuraClient:
        options.setdefault("timeout", 5)
        return aura.AsyncAuraClient(
            client_id="local-id",
            client_secret="local-secret",
            base_url=self.url,
            allow_insecure_base_url=True,
            **options,
        )

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                parts = urlsplit(self.path)
                received = Received(
                    method=self.command,
                    path=parts.path,
                    query=parts.query,
                    headers={k.lower(): v for k, v in self.headers.items()},
                    body=self.rfile.read(length) if length else b"",
                )
                fake.received.append(received)
                route = fake.routes.get((self.command, parts.path))
                reply = (
                    Reply.json(404, {"errors": [{"message": "no route"}]})
                    if route is None
                    else (route(received) if callable(route) else route)
                )
                if reply.delay:
                    time.sleep(reply.delay)
                self.send_response(reply.status)
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(reply.body)))
                self.end_headers()
                if reply.body:
                    self.wfile.write(reply.body)

            do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _serve  # noqa: N815 - stdlib names

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def fake_aura() -> Iterator[FakeAura]:
    server = FakeAura()
    server.start()
    yield server
    server.stop()
