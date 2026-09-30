from typing import Any

import pytest

from aura_python_sdk import AuraConfigurationError
from aura_python_sdk._config import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RESPONSE_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    ClientConfig,
    build_config,
)


def _config(**overrides: Any) -> ClientConfig:
    options: dict[str, Any] = {
        "client_id": "id",
        "client_secret": "secret",
        "base_url": DEFAULT_BASE_URL,
        "allow_insecure_base_url": False,
        "timeout": DEFAULT_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "max_response_size": DEFAULT_MAX_RESPONSE_SIZE,
        "user_agent": DEFAULT_USER_AGENT,
        "default_headers": None,
    }
    options.update(overrides)
    return build_config(**options)


def test_defaults_match_go_sdk() -> None:
    config = _config()
    assert config.base_url == "https://api.neo4j.io"
    assert config.timeout == 120.0
    assert config.max_retries == 3
    assert config.max_response_size == 10 * 1024 * 1024
    assert config.user_agent.startswith("aura-python-sdk/")
    assert config.default_headers == {}


def test_secret_is_not_in_repr() -> None:
    assert "super-secret" not in repr(_config(client_secret="super-secret"))


@pytest.mark.parametrize("field", ["client_id", "client_secret"])
@pytest.mark.parametrize("value", ["", None])
def test_credentials_required(field: str, value: object) -> None:
    with pytest.raises(AuraConfigurationError, match="must not be empty"):
        _config(**{field: value})


def test_base_url_requires_https() -> None:
    with pytest.raises(AuraConfigurationError, match="HTTPS"):
        _config(base_url="http://localhost:8080")


def test_insecure_base_url_allowed_when_opted_in() -> None:
    config = _config(base_url="http://localhost:8080/", allow_insecure_base_url=True)
    assert config.base_url == "http://localhost:8080"


@pytest.mark.parametrize(
    "base_url",
    ["", "api.neo4j.io", "ftp://api.neo4j.io", "https://", "https://x?y=1", "https://x#f"],
)
def test_invalid_base_urls(base_url: str) -> None:
    with pytest.raises(AuraConfigurationError):
        _config(base_url=base_url, allow_insecure_base_url=True)


def test_trailing_slash_is_stripped() -> None:
    assert (
        _config(base_url="https://staging.example.com/").base_url == "https://staging.example.com"
    )


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True, "10"])
def test_invalid_timeout(timeout: object) -> None:
    with pytest.raises(AuraConfigurationError, match="timeout"):
        _config(timeout=timeout)


def test_integer_timeout_is_accepted() -> None:
    assert _config(timeout=5).timeout == 5.0


def test_zero_retries_is_allowed() -> None:
    assert _config(max_retries=0).max_retries == 0


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_invalid_max_retries(value: object) -> None:
    with pytest.raises(AuraConfigurationError, match="max retries"):
        _config(max_retries=value)


@pytest.mark.parametrize("value", [0, -1, 1.5])
def test_invalid_max_response_size(value: object) -> None:
    with pytest.raises(AuraConfigurationError, match="max response size"):
        _config(max_response_size=value)


@pytest.mark.parametrize("value", ["", "agent\r\nX-Evil: 1"])
def test_invalid_user_agent(value: str) -> None:
    with pytest.raises(AuraConfigurationError, match="user agent"):
        _config(user_agent=value)


def test_protected_default_headers_are_dropped() -> None:
    config = _config(
        default_headers={
            "authorization": "Bearer stolen",
            "Content-Type": "text/plain",
            "USER-AGENT": "other",
            "X-Trace": "abc",
        }
    )
    assert config.default_headers == {"X-Trace": "abc"}


@pytest.mark.parametrize(
    "headers", [{"": "v"}, {"X-A:B": "v"}, {"X-A": "line\nbreak"}, {"X-A": 1}, {1: "v"}]
)
def test_malformed_default_headers_rejected(headers: dict[Any, Any]) -> None:
    with pytest.raises(AuraConfigurationError):
        _config(default_headers=headers)
