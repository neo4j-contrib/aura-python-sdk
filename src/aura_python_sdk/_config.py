"""Client option defaults and validation (Go: the With* functional options in client.go)."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from aura_python_sdk._errors import AuraConfigurationError
from aura_python_sdk._version import __version__

# The Aura API version this client targets. It is deliberately not configurable.
API_VERSION = "v1"

DEFAULT_BASE_URL = "https://api.neo4j.io"
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024
DEFAULT_USER_AGENT = f"aura-python-sdk/{__version__}"

# Headers that default_headers may not override (compared case-insensitively).
PROTECTED_HEADERS = frozenset({"authorization", "content-type", "user-agent"})


@dataclass(frozen=True, slots=True)
class ClientConfig:
    client_id: str
    client_secret: str = field(repr=False)
    base_url: str
    allow_insecure_base_url: bool
    timeout: float
    max_retries: int
    max_response_size: int
    user_agent: str
    # A caller may put their own secret here, such as a proxy key.
    default_headers: Mapping[str, str] = field(repr=False)


def build_config(
    *,
    client_id: str,
    client_secret: str,
    base_url: str,
    allow_insecure_base_url: bool,
    timeout: float,
    max_retries: int,
    max_response_size: int,
    user_agent: str,
    default_headers: Mapping[str, str] | None,
) -> ClientConfig:
    """Validate every option and raise AuraConfigurationError on the first bad one."""
    if not isinstance(client_id, str) or not client_id:
        raise AuraConfigurationError("client ID must not be empty")
    if not isinstance(client_secret, str) or not client_secret:
        raise AuraConfigurationError("client secret must not be empty")

    return ClientConfig(
        client_id=client_id,
        client_secret=client_secret,
        base_url=_validate_base_url(base_url, allow_insecure=allow_insecure_base_url),
        allow_insecure_base_url=bool(allow_insecure_base_url),
        timeout=_validate_timeout(timeout),
        max_retries=_validate_non_negative_int("max retries", max_retries),
        max_response_size=_validate_positive_int("max response size", max_response_size),
        user_agent=_validate_header_value("user agent", user_agent, allow_empty=False),
        default_headers=_filter_default_headers(default_headers),
    )


def override_config(
    config: ClientConfig, *, timeout: float | None, max_retries: int | None
) -> ClientConfig:
    """A copy of ``config`` with the options ``with_options`` can change, validated the same way."""
    return dataclasses.replace(
        config,
        timeout=config.timeout if timeout is None else _validate_timeout(timeout),
        max_retries=(
            config.max_retries
            if max_retries is None
            else _validate_non_negative_int("max retries", max_retries)
        ),
    )


def _validate_base_url(base_url: str, *, allow_insecure: bool) -> str:
    if not isinstance(base_url, str) or not base_url:
        raise AuraConfigurationError("base URL must not be empty")
    parts = urlsplit(base_url)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        raise AuraConfigurationError(f"base URL is not a valid http(s) URL: {base_url!r}")
    if parts.scheme != "https" and not allow_insecure:
        raise AuraConfigurationError(
            "base URL must use HTTPS to protect credentials in transit "
            "(pass allow_insecure_base_url=True only for local testing)"
        )
    if parts.query or parts.fragment:
        raise AuraConfigurationError("base URL must not contain a query string or fragment")
    return base_url.rstrip("/")


def _validate_timeout(timeout: float) -> float:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise AuraConfigurationError("timeout must be a finite number of seconds greater than zero")
    return float(timeout)


def _validate_non_negative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuraConfigurationError(f"{name} must be an integer of zero or more")
    return value


def _validate_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AuraConfigurationError(f"{name} must be an integer greater than zero")
    return value


def _validate_header_value(name: str, value: str, *, allow_empty: bool) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise AuraConfigurationError(f"{name} must be a non-empty string")
    if "\r" in value or "\n" in value:
        raise AuraConfigurationError(f"{name} must not contain line breaks")
    return value


def _filter_default_headers(headers: Mapping[str, str] | None) -> Mapping[str, str]:
    """Drop protected headers silently, as the Go SDK does, and reject malformed ones."""
    if not headers:
        return {}
    filtered: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not key or any(c in key for c in "\r\n:"):
            raise AuraConfigurationError(f"invalid default header name: {key!r}")
        _validate_header_value(f"default header {key!r}", value, allow_empty=True)
        if key.lower() not in PROTECTED_HEADERS:
            filtered[key] = value
    return filtered
