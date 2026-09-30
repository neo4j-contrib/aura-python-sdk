import base64
import logging
import typing

import pytest

import aura_python_sdk as aura
from aura_python_sdk import AuraClient, AuraConfigurationError
from aura_python_sdk._client import _AsyncClientOptions, _ClientOptions
from aura_python_sdk._internal.http._httpx import HttpxTransport
from tests.fakes import FakeTransport, json_response, token_response


def test_construct_with_fake_transport_and_make_a_call() -> None:
    transport = FakeTransport([token_response("tok"), json_response(200, {"data": []})])
    client = AuraClient(client_id="id", client_secret="secret", transport=transport)

    client._api.get("tenants")

    [request] = transport.api_requests
    assert request.url == "https://api.neo4j.io/v1/tenants"
    assert request.headers["User-Agent"] == f"aura-python-sdk/{aura.__version__}"
    assert transport.requests[0].url == "https://api.neo4j.io/oauth/token"


def test_options_are_wired_through() -> None:
    transport = FakeTransport([token_response(), json_response(200, {})])
    client = AuraClient(
        client_id="id",
        client_secret="secret",
        base_url="http://localhost:9000",
        allow_insecure_base_url=True,
        timeout=7,
        max_response_size=2048,
        user_agent="my-app/2",
        default_headers={"X-Team": "db"},
        transport=transport,
    )
    client._api.get("instances")

    token_request, api_request = transport.requests
    assert token_request.url == "http://localhost:9000/oauth/token"
    assert api_request.url == "http://localhost:9000/v1/instances"
    assert api_request.timeout == pytest.approx(7, abs=0.5)
    assert api_request.max_response_size == 2048
    assert api_request.headers["User-Agent"] == "my-app/2"
    assert api_request.headers["X-Team"] == "db"
    assert client.base_url == "http://localhost:9000"


def test_invalid_option_raises_configuration_error() -> None:
    with pytest.raises(AuraConfigurationError):
        AuraClient(client_id="", client_secret="secret")
    assert issubclass(AuraConfigurationError, ValueError)


def test_rejects_non_transport() -> None:
    with pytest.raises(AuraConfigurationError, match="transport"):
        AuraClient(client_id="id", client_secret="s", transport=object())  # type: ignore[arg-type]


def test_rejects_non_logger() -> None:
    with pytest.raises(AuraConfigurationError, match="logger"):
        AuraClient(client_id="id", client_secret="s", logger="debug")  # type: ignore[arg-type]


def test_default_transport_is_httpx_and_owned() -> None:
    client = AuraClient(client_id="id", client_secret="secret")
    assert isinstance(client._transport, HttpxTransport)
    client.close()
    client.close()  # idempotent


def test_context_manager_closes_owned_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(HttpxTransport, "close", lambda self: closed.append(True))
    with AuraClient(client_id="id", client_secret="secret"):
        pass
    assert closed == [True]


def test_does_not_close_caller_transport() -> None:
    transport = FakeTransport()
    with AuraClient(client_id="id", client_secret="secret", transport=transport):
        pass
    assert transport.closed is False


@pytest.mark.parametrize("owned", [True, False])
def test_call_after_close_raises_client_closed(owned: bool) -> None:
    transport = None if owned else FakeTransport()
    client = AuraClient(client_id="id", client_secret="secret", transport=transport)
    client.close()
    with pytest.raises(aura.AuraClientClosedError, match="client is closed") as info:
        client.instances.list()
    # Catchable as an SDK error, and as the RuntimeError httpx used to raise.
    assert isinstance(info.value, aura.AuraError)
    assert isinstance(info.value, RuntimeError)
    if transport is not None:
        assert transport.requests == []


def test_repr_hides_credentials() -> None:
    client = AuraClient(client_id="id-123", client_secret="s3cr3t", transport=FakeTransport())
    assert "s3cr3t" not in repr(client)
    assert repr(client) == "AuraClient(base_url='https://api.neo4j.io')"


@pytest.mark.parametrize(
    ("client_class", "options"),
    [(aura.AuraClient, _ClientOptions), (aura.AsyncAuraClient, _AsyncClientOptions)],
)
def test_from_env_options_match_constructor(client_class: type, options: type) -> None:
    # from_env's typed options must list every constructor option except the credentials,
    # with the same types, or type checkers would reject (or miss) a valid option.
    hints = typing.get_type_hints(vars(client_class)["__init__"])
    expected = {k: v for k, v in hints.items() if k not in ("client_id", "client_secret", "return")}
    assert typing.get_type_hints(options) == expected


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AURA_CLIENT_ID", "env-id")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "env-secret")
    transport = FakeTransport([token_response(), json_response(200, {})])
    client = AuraClient.from_env(transport=transport, timeout=10)
    client._api.get("tenants")
    assert transport.requests[0].headers["Authorization"].startswith("Basic ")


@pytest.mark.parametrize("missing", ["AURA_CLIENT_ID", "AURA_CLIENT_SECRET"])
def test_from_env_requires_both(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setenv("AURA_CLIENT_ID", "env-id")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "env-secret")
    monkeypatch.delenv(missing)
    with pytest.raises(AuraConfigurationError, match="must both be set"):
        AuraClient.from_env()


def test_library_logger_has_null_handler() -> None:
    handlers = logging.getLogger("aura_python_sdk").handlers
    assert any(isinstance(h, logging.NullHandler) for h in handlers)


def test_secrets_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    transport = FakeTransport([token_response("tok-value"), json_response(200, {})])
    client = AuraClient(client_id="id", client_secret="s3cr3t", transport=transport)
    with caplog.at_level(logging.DEBUG, logger="aura_python_sdk"):
        client._api.get("instances")
    text = "\n".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert caplog.records
    assert "s3cr3t" not in text
    assert "tok-value" not in text


def test_request_repr_hides_credentials() -> None:
    # A custom transport that logs its requests must not write credentials to the log.
    transport = FakeTransport([token_response("tok-value"), json_response(200, {})])
    client = AuraClient(client_id="id", client_secret="s3cr3t", transport=transport)
    client._api.get("instances")
    token_request, api_request = transport.requests
    basic = base64.b64encode(b"id:s3cr3t").decode()
    assert basic in token_request.headers["Authorization"]
    assert basic not in repr(token_request)
    assert "tok-value" not in repr(api_request)
    assert "'Authorization': '***'" in repr(api_request)
    assert "'User-Agent'" in repr(api_request)
