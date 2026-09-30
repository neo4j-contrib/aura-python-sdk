"""SDK errors should read cleanly: a public class name and a short traceback."""

import traceback

import pytest

import aura_python_sdk as aura
from tests.fakes import FakeAsyncTransport, FakeTransport, json_response, token_response

FORBIDDEN = json_response(
    403, {"errors": [{"message": "Insufficient permissions", "reason": "unauthorized"}]}
)


def _frames(exc: BaseException) -> list[str]:
    return [frame.filename for frame in traceback.extract_tb(exc.__traceback__)]


def test_public_exceptions_report_the_package_path() -> None:
    for name in aura.__all__:
        obj = getattr(aura, name)
        if isinstance(obj, type) and issubclass(obj, BaseException):
            assert obj.__module__ == "aura_python_sdk", name
    line = traceback.format_exception_only(aura.NotFoundError(404, "Not Found"))[-1]
    assert line.startswith("aura_python_sdk.NotFoundError: API error (status 404)")


def test_api_error_traceback_skips_internal_frames() -> None:
    transport = FakeTransport([token_response(), FORBIDDEN])
    client = aura.AuraClient(client_id="id", client_secret="secret", transport=transport)
    with pytest.raises(aura.PermissionDeniedError) as info:
        client.cmek.list()

    frames = _frames(info.value)
    assert not any("/_internal/" in f for f in frames), frames
    # What remains: this test, the public service method, and the re-raise in _run.
    assert any(f.endswith("services/cmek.py") for f in frames)


@pytest.mark.anyio
async def test_async_api_error_traceback_skips_internal_frames() -> None:
    transport = FakeAsyncTransport([token_response(), FORBIDDEN])
    client = aura.AsyncAuraClient(client_id="id", client_secret="secret", transport=transport)
    with pytest.raises(aura.PermissionDeniedError) as info:
        await client.cmek.list()
    assert not any("/_internal/" in f for f in _frames(info.value))


def test_network_error_keeps_its_cause() -> None:
    cause = OSError("connection reset")
    error = aura.AuraConnectionError("request failed", request_sent=False)
    error.__cause__ = cause
    transport = FakeTransport([token_response(), error])
    client = aura.AuraClient(
        client_id="id", client_secret="secret", transport=transport, max_retries=0
    )
    with pytest.raises(aura.AuraConnectionError) as info:
        client.tenants.list()
    assert info.value.__cause__ is cause


def test_unexpected_errors_keep_their_full_traceback() -> None:
    def explode(request: aura.HttpRequest) -> aura.HttpResponse:
        raise RuntimeError("bug in a custom transport")

    transport = FakeTransport([token_response(), explode])
    client = aura.AuraClient(client_id="id", client_secret="secret", transport=transport)
    with pytest.raises(RuntimeError) as info:
        client.tenants.list()
    assert any("/_internal/" in f for f in _frames(info.value))
