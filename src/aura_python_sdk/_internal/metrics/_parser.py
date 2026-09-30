"""Parser for the Prometheus text exposition format (version 0.0.4).

The keys and values match the Go SDK, which uses ``expfmt.TextParser``:

- Metrics are keyed by their ``# TYPE`` name. A counter declared as ``foo_total`` stays
  ``foo_total``, and a counter declared as ``foo`` stays ``foo``.
- A summary or histogram becomes one entry per label set, keyed by its base name, with the
  ``_sum`` sample as its value. The quantile, bucket and ``_count`` lines are skipped.
- A sample without a ``# TYPE`` line is untyped and keyed by its own name.
- Timestamps stay in milliseconds.
"""

from __future__ import annotations

import re

from aura_python_sdk._errors import AuraResponseError
from aura_python_sdk.models.prometheus import PrometheusMetric

_NAME = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
_LABEL_NAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_ESCAPES = {"\\": "\\", '"': '"', "n": "\n"}
_AGGREGATE_TYPES = frozenset({"summary", "histogram"})
_AGGREGATE_SUFFIXES = ("_sum", "_count", "_bucket")


class _ParseError(Exception):
    pass


def parse_exposition(text: str) -> dict[str, tuple[PrometheusMetric, ...]]:
    """Parse exposition text into metrics keyed by name. Raises AuraResponseError if malformed."""
    types: dict[str, str] = {}
    grouped: dict[str, list[PrometheusMetric]] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line[1:].split(None, 2)
            if len(parts) == 3 and parts[0] == "TYPE":
                types[parts[1]] = parts[2].strip().lower()
            continue
        try:
            name, labels, value, timestamp_ms = _parse_sample(line)
        except _ParseError as exc:
            raise AuraResponseError(f"invalid Prometheus metrics at line {lineno}: {exc}") from None

        key = _metric_key(name, types)
        if key is None:
            continue
        grouped.setdefault(key, []).append(
            PrometheusMetric(name=key, labels=labels, value=value, timestamp_ms=timestamp_ms)
        )
    return {name: tuple(samples) for name, samples in grouped.items()}


def _metric_key(sample_name: str, types: dict[str, str]) -> str | None:
    """The metric key a sample belongs to, or None if the Go SDK would not report it."""
    if types.get(sample_name) in _AGGREGATE_TYPES:
        return None  # a quantile line of a summary
    for suffix in _AGGREGATE_SUFFIXES:
        base = sample_name.removesuffix(suffix)
        if base != sample_name and types.get(base) in _AGGREGATE_TYPES:
            return base if suffix == "_sum" else None
    return sample_name


def _parse_sample(line: str) -> tuple[str, dict[str, str], float, int | None]:
    match = _NAME.match(line)
    if not match:
        raise _ParseError("expected a metric name")
    name = match.group()
    pos = match.end()

    labels: dict[str, str] = {}
    if pos < len(line) and line[pos] == "{":
        labels, pos = _parse_labels(line, pos + 1)

    fields = line[pos:].split()
    if len(fields) not in (1, 2):
        raise _ParseError("expected a value and an optional timestamp")
    try:
        value = float(fields[0])
    except ValueError:
        raise _ParseError(f"invalid value {fields[0]!r}") from None
    timestamp_ms = None
    if len(fields) == 2:
        try:
            timestamp_ms = int(fields[1])
        except ValueError:
            raise _ParseError(f"invalid timestamp {fields[1]!r}") from None
    return name, labels, value, timestamp_ms


def _parse_labels(line: str, pos: int) -> tuple[dict[str, str], int]:
    """Parse ``name="value",...}`` starting after the opening brace. Returns (labels, end)."""
    labels: dict[str, str] = {}
    while True:
        pos = _skip_spaces(line, pos)
        if pos < len(line) and line[pos] == "}":
            return labels, pos + 1
        match = _LABEL_NAME.match(line, pos)
        if not match:
            raise _ParseError("expected a label name")
        label = match.group()
        pos = _expect(line, _skip_spaces(line, match.end()), "=", label)
        pos = _expect(line, _skip_spaces(line, pos), '"', label)
        value, pos = _parse_label_value(line, pos)
        labels[label] = value
        pos = _skip_spaces(line, pos)
        if pos < len(line) and line[pos] == ",":
            pos += 1
        elif pos >= len(line) or line[pos] != "}":
            raise _ParseError("expected ',' or '}' after a label")


def _parse_label_value(line: str, pos: int) -> tuple[str, int]:
    chars: list[str] = []
    while pos < len(line):
        char = line[pos]
        if char == "\\":
            escaped = line[pos + 1 : pos + 2]
            if escaped not in _ESCAPES:
                raise _ParseError(f"invalid escape sequence \\{escaped}")
            chars.append(_ESCAPES[escaped])
            pos += 2
        elif char == '"':
            return "".join(chars), pos + 1
        else:
            chars.append(char)
            pos += 1
    raise _ParseError("unterminated label value")


def _expect(line: str, pos: int, char: str, label: str) -> int:
    if line[pos : pos + 1] != char:
        raise _ParseError(f"expected {char!r} in label {label!r}")
    return pos + 1


def _skip_spaces(line: str, pos: int) -> int:
    while pos < len(line) and line[pos] in " \t":
        pos += 1
    return pos
