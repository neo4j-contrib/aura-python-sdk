import math

import pytest

from aura_python_sdk import AuraResponseError, PrometheusMetric
from aura_python_sdk._internal.metrics._parser import parse_exposition


def test_gauge_with_labels_and_help() -> None:
    text = """
# HELP neo4j_aura_cpu_usage CPU usage (cores)
# TYPE neo4j_aura_cpu_usage gauge
neo4j_aura_cpu_usage{availability_zone="europe-west2-c",instance_id="c9f0d13a"} 0.023206
neo4j_aura_cpu_usage{availability_zone="europe-west2-b",instance_id="c9f0d13a"} 0.5
"""
    metrics = parse_exposition(text)
    assert list(metrics) == ["neo4j_aura_cpu_usage"]
    first, second = metrics["neo4j_aura_cpu_usage"]
    assert first == PrometheusMetric(
        name="neo4j_aura_cpu_usage",
        labels={"availability_zone": "europe-west2-c", "instance_id": "c9f0d13a"},
        value=0.023206,
    )
    assert second.value == 0.5


def test_counters_keep_their_type_line_name() -> None:
    # prometheus_client would rename plain_counter to plain_counter_total; expfmt (Go) does not.
    text = """
# TYPE neo4j_db_query_execution_success_total counter
neo4j_db_query_execution_success_total{db="neo4j"} 42
# TYPE plain_counter counter
plain_counter 7
"""
    metrics = parse_exposition(text)
    assert set(metrics) == {"neo4j_db_query_execution_success_total", "plain_counter"}
    assert metrics["plain_counter"][0].value == 7


def test_summary_and_histogram_use_sum_per_label_set() -> None:
    text = """
# TYPE latency summary
latency{db="a",quantile="0.5"} 1
latency{db="a",quantile="0.99"} 9
latency_sum{db="a"} 10
latency_count{db="a"} 4
latency_sum{db="b"} 20
latency_count{db="b"} 5
# TYPE sizes histogram
sizes_bucket{le="1"} 1
sizes_bucket{le="+Inf"} 2
sizes_sum 3.5
sizes_count 2
"""
    metrics = parse_exposition(text)
    assert set(metrics) == {"latency", "sizes"}
    assert [(m.labels, m.value) for m in metrics["latency"]] == [
        ({"db": "a"}, 10),
        ({"db": "b"}, 20),
    ]
    assert metrics["sizes"][0].value == 3.5


def test_untyped_samples_are_keyed_by_name() -> None:
    metrics = parse_exposition("some_metric 1\nsome_metric_sum 2\n")
    assert set(metrics) == {"some_metric", "some_metric_sum"}


def test_special_values_and_timestamps() -> None:
    text = "a NaN\nb +Inf 1700000000000\nc -Inf -5\nd 1.5e3\n"
    metrics = parse_exposition(text)
    assert math.isnan(metrics["a"][0].value)
    assert metrics["b"][0].value == math.inf
    assert metrics["b"][0].timestamp_ms == 1700000000000
    assert metrics["c"][0].value == -math.inf
    assert metrics["c"][0].timestamp_ms == -5
    assert metrics["d"][0].value == 1500.0
    assert metrics["d"][0].timestamp_ms is None


def test_label_escapes_spacing_and_trailing_comma() -> None:
    text = r'm{ a = "q\"uote" , b="back\\slash",c="new\nline", } 1'
    [metric] = parse_exposition(text)["m"]
    assert metric.labels == {"a": 'q"uote', "b": "back\\slash", "c": "new\nline"}


def test_empty_labels_and_braces_inside_values() -> None:
    [metric] = parse_exposition('m{} 1\nn{path="/a{b}c"} 2')["m"]
    assert metric.labels == {}
    assert parse_exposition('n{path="/a{b}c"} 2')["n"][0].labels == {"path": "/a{b}c"}


def test_comments_and_blank_lines_are_ignored() -> None:
    text = "# just a comment\n\n# HELP x help text\n# TYPE\nx 1\n"
    assert parse_exposition(text)["x"][0].value == 1


def test_empty_input() -> None:
    assert parse_exposition("") == {}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("9bad 1", "expected a metric name"),
        ("m", "expected a value"),
        ("m 1 2 3", "expected a value"),
        ("m abc", "invalid value"),
        ("m 1 soon", "invalid timestamp"),
        ('m{a="1" 1', "expected ',' or '}'"),
        ("m{a=1} 1", "expected '\"'"),
        ('m{a "1"} 1', "expected '='"),
        ('m{="1"} 1', "expected a label name"),
        ('m{a="unterminated} 1', "unterminated label value"),
        (r'm{a="bad\tescape"} 1', "invalid escape"),
    ],
)
def test_malformed_lines(text: str, message: str) -> None:
    with pytest.raises(AuraResponseError, match="line 1") as info:
        parse_exposition(text)
    assert message in str(info.value)


def test_error_reports_line_number() -> None:
    with pytest.raises(AuraResponseError, match="line 3"):
        parse_exposition("a 1\nb 2\nc oops\n")
