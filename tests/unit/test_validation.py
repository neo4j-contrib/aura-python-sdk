import pytest

from aura_python_sdk import AuraValidationError
from aura_python_sdk import _validation as validate


@pytest.mark.parametrize("value", ["2f49c2b3", "ABCDEF12"])
def test_valid_instance_ids(value: str) -> None:
    assert validate.instance_id(value) == value


@pytest.mark.parametrize(
    "value", ["", "   ", None, 12345678, "2f49c2b", "2f49c2b33", "zzzzzzzz", "../abcde"]
)
def test_invalid_instance_ids(value: object) -> None:
    with pytest.raises(AuraValidationError, match="instance ID"):
        validate.instance_id(value)


def test_instance_id_custom_name_in_message() -> None:
    with pytest.raises(AuraValidationError, match="source instance ID must not be empty"):
        validate.instance_id("", "source instance ID")


@pytest.mark.parametrize("check", [validate.tenant_id, validate.snapshot_id])
def test_uuid_ids(check: object) -> None:
    assert check("6981ace7-efe8-4f5c-b7c5-267b5162ce91") == "6981ace7-efe8-4f5c-b7c5-267b5162ce91"  # type: ignore[operator]
    for bad in ["", "6981ace7", "6981ace7-efe8-4f5c-b7c5-267b5162ce9Z", "2023-01-20T13:44:42Z"]:
        with pytest.raises(AuraValidationError, match="ID"):
            check(bad)  # type: ignore[operator]


def test_uuid_error_message_matches_go() -> None:
    with pytest.raises(AuraValidationError) as info:
        validate.tenant_id("nope")
    assert str(info.value) == (
        "tenant ID must be a valid UUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
    )


def test_session_id_only_needs_to_be_non_empty() -> None:
    assert validate.session_id("s-04de43fe-67ab-4") == "s-04de43fe-67ab-4"
    with pytest.raises(AuraValidationError, match="GDS session ID must not be empty"):
        validate.session_id("")


def test_instance_name_length() -> None:
    assert validate.instance_name("x" * 30) == "x" * 30
    with pytest.raises(AuraValidationError, match="at most 30 characters"):
        validate.instance_name("x" * 31)


@pytest.mark.parametrize("value", [-1, 1.5, True, "3"])
def test_non_negative_int(value: object) -> None:
    assert validate.non_negative_int("count", 0) == 0
    with pytest.raises(AuraValidationError, match="count must be an integer"):
        validate.non_negative_int("count", value)


def test_validation_error_is_value_error() -> None:
    assert issubclass(AuraValidationError, ValueError)
