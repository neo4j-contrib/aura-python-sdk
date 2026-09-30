"""Client-side argument validation, run before any request is sent (Go: internal/utils)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from aura_python_sdk._errors import AuraValidationError

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_INSTANCE_ID = re.compile(r"[0-9a-fA-F]{8}")

MAX_NAME_LENGTH = 30


def require_non_empty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuraValidationError(f"{name} must not be empty")
    return value


def _uuid(name: str, value: object) -> str:
    value = require_non_empty(name, value)
    if not _UUID.fullmatch(value):
        raise AuraValidationError(
            f"{name} must be a valid UUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        )
    return value


def instance_id(value: object, name: str = "instance ID") -> str:
    value = require_non_empty(name, value)
    if not _INSTANCE_ID.fullmatch(value):
        raise AuraValidationError(
            f"{name} must be in the format of a 8-character hex string (xxxxxxxx)"
        )
    return value


def tenant_id(value: object, name: str = "tenant ID") -> str:
    return _uuid(name, value)


def snapshot_id(value: object, name: str = "snapshot ID") -> str:
    return _uuid(name, value)


def session_id(value: object) -> str:
    return require_non_empty("GDS session ID", value)


def display_name(label: str, value: object) -> str:
    """An instance or key name: 1-30 characters with no leading or trailing whitespace."""
    value = require_non_empty(label, value)
    if len(value) > MAX_NAME_LENGTH:
        raise AuraValidationError(f"{label} must be at most {MAX_NAME_LENGTH} characters long")
    if value != value.strip():
        raise AuraValidationError(f"{label} must not have leading or trailing whitespace")
    return value


def instance_name(value: object) -> str:
    return display_name("instance name", value)


def non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuraValidationError(f"{name} must be an integer of zero or more")
    return value


def boolean(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise AuraValidationError(f"{name} must be True or False")
    return value


def string_list(name: str, value: Sequence[str]) -> list[str]:
    """A sequence of non-empty strings. A bare string is rejected, not split into characters."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise AuraValidationError(f"{name} must be a sequence of strings")
    return [require_non_empty(f"{name} entry", item) for item in value]
