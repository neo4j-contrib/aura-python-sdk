from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

import pytest

from aura_python_sdk import AuraResponseError
from aura_python_sdk._internal._serde import from_json, parse_data, parse_data_list, to_json


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True, slots=True, kw_only=True)
class Child:
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Sample:
    id: str
    count: int
    ratio: float
    flag: bool
    colour: Colour | str
    strict_colour: Colour | None = None
    when: datetime | None = None
    day: date | None = None
    note: str | None = None
    children: tuple[Child, ...] = ()
    tags: list[str] = field(default_factory=list)


BASE = {"id": "a", "count": 1, "ratio": 0.5, "flag": True, "colour": "red"}


def _sample(**overrides: object) -> Sample:
    return from_json(Sample, {**BASE, **overrides})


def test_basic_conversion() -> None:
    sample = _sample(
        when="2024-01-31T14:06:57Z",
        day="2024-01-31",
        children=[{"name": "x"}, {"name": "y"}],
        tags=["t1"],
    )
    assert sample == Sample(
        id="a",
        count=1,
        ratio=0.5,
        flag=True,
        colour=Colour.RED,
        when=datetime(2024, 1, 31, 14, 6, 57, tzinfo=UTC),
        day=date(2024, 1, 31),
        children=(Child(name="x"), Child(name="y")),
        tags=["t1"],
    )


def test_unknown_enum_value_is_kept_as_string() -> None:
    sample = _sample(colour="green")
    assert sample.colour == "green"
    assert not isinstance(sample.colour, Colour)


def test_known_enum_value_is_member_and_compares_as_string() -> None:
    assert _sample(colour="blue").colour is Colour.BLUE
    assert _sample(colour="blue").colour == "blue"


def test_enum_without_str_fallback_rejects_unknown() -> None:
    with pytest.raises(AuraResponseError, match=r"strict_colour: 'green' is not a valid Colour"):
        _sample(strict_colour="green")


def test_unknown_keys_are_ignored() -> None:
    assert _sample(brand_new_field={"x": 1}).id == "a"


def test_missing_optional_uses_default() -> None:
    sample = _sample()
    assert sample.note is None
    assert sample.children == ()
    assert sample.tags == []


def test_null_optional_is_none() -> None:
    assert _sample(note=None, when=None).note is None


def test_empty_string_timestamp_is_none() -> None:
    assert _sample(when="").when is None


def test_missing_required_field() -> None:
    payload = dict(BASE)
    del payload["count"]
    with pytest.raises(AuraResponseError, match="count: required field is missing"):
        from_json(Sample, payload)


def test_null_required_field() -> None:
    with pytest.raises(AuraResponseError, match="id: value must not be null"):
        _sample(id=None)


def test_nested_error_path() -> None:
    with pytest.raises(AuraResponseError, match=r"children\[1\]\.name: required field is missing"):
        _sample(children=[{"name": "ok"}, {}])


@pytest.mark.parametrize(("value", "expected"), [(3, 3), (3.0, 3), ("42", 42), ("-2", -2)])
def test_int_tolerance(value: object, expected: int) -> None:
    assert _sample(count=value).count == expected


@pytest.mark.parametrize("value", [True, 3.5, "4GB", "", [1]])
def test_int_rejects(value: object) -> None:
    with pytest.raises(AuraResponseError, match="count: expected an integer"):
        _sample(count=value)


def test_float_accepts_int_but_not_bool() -> None:
    assert _sample(ratio=2).ratio == 2.0
    with pytest.raises(AuraResponseError, match="ratio"):
        _sample(ratio=False)


def test_str_accepts_number() -> None:
    assert _sample(id=123).id == "123"


@pytest.mark.parametrize("value", [True, {"a": 1}, ["x"]])
def test_str_rejects(value: object) -> None:
    with pytest.raises(AuraResponseError, match="id: expected a string"):
        _sample(id=value)


@pytest.mark.parametrize("value", ["true", 1, 0])
def test_bool_is_strict(value: object) -> None:
    with pytest.raises(AuraResponseError, match="flag: expected a boolean"):
        _sample(flag=value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2023-01-20T13:44:42Z", datetime(2023, 1, 20, 13, 44, 42, tzinfo=UTC)),
        ("2023-01-20T13:44:42.123Z", datetime(2023, 1, 20, 13, 44, 42, 123000, tzinfo=UTC)),
        # Go RFC3339Nano: nine fractional digits are truncated to microseconds.
        (
            "2023-01-20T13:44:42.123456789Z",
            datetime(2023, 1, 20, 13, 44, 42, 123456, tzinfo=UTC),
        ),
        ("2023-01-20T13:44:42+00:00", datetime(2023, 1, 20, 13, 44, 42, tzinfo=UTC)),
    ],
)
def test_timestamps(value: str, expected: datetime) -> None:
    assert _sample(when=value).when == expected


@pytest.mark.parametrize("value", ["yesterday", 1700000000, "2023-13-01T00:00:00Z"])
def test_invalid_timestamp(value: object) -> None:
    with pytest.raises(AuraResponseError, match="when: expected an ISO 8601 timestamp"):
        _sample(when=value)


@pytest.mark.parametrize("value", ["31/01/2024", 20240131])
def test_invalid_date(value: object) -> None:
    with pytest.raises(AuraResponseError, match="day: expected an ISO date"):
        _sample(day=value)


def test_null_for_non_optional_union() -> None:
    with pytest.raises(AuraResponseError, match="colour: value must not be null"):
        _sample(colour=None)


def test_non_object_and_non_list() -> None:
    with pytest.raises(AuraResponseError, match="<root>: expected an object, got list"):
        from_json(Sample, [])
    with pytest.raises(AuraResponseError, match="children: expected a list"):
        _sample(children={"name": "x"})


def test_parse_data_unwraps() -> None:
    assert parse_data(Child, {"data": {"name": "x"}}) == Child(name="x")
    assert parse_data_list(Child, {"data": [{"name": "x"}]}) == [Child(name="x")]


@pytest.mark.parametrize("payload", [{}, {"items": []}, [], None, "data"])
def test_parse_data_requires_data_key(payload: object) -> None:
    with pytest.raises(AuraResponseError, match="missing 'data'"):
        parse_data(Child, payload)


def test_parse_data_list_requires_list() -> None:
    with pytest.raises(AuraResponseError, match="expected a list"):
        parse_data_list(Child, {"data": {"name": "x"}})


def test_unsupported_field_type_is_a_programming_error() -> None:
    @dataclass
    class Bad:
        value: bytes

    with pytest.raises(TypeError, match="unsupported model field type"):
        from_json(Bad, {"value": "x"})


def test_to_json_omits_none_and_converts_values() -> None:
    sample = Sample(
        id="a",
        count=1,
        ratio=0.5,
        flag=False,
        colour=Colour.BLUE,
        when=datetime(2024, 1, 31, 14, 6, 57, tzinfo=UTC),
        day=date(2024, 1, 31),
        children=(Child(name="x"),),
    )
    assert to_json(sample) == {
        "id": "a",
        "count": 1,
        "ratio": 0.5,
        "flag": False,
        "colour": "blue",
        "when": "2024-01-31T14:06:57+00:00",
        "day": "2024-01-31",
        "children": [{"name": "x"}],
        "tags": [],
    }


def test_to_json_mapping_drops_none() -> None:
    assert to_json({"name": "x", "memory": None, "colour": Colour.RED}) == {
        "name": "x",
        "colour": "red",
    }
