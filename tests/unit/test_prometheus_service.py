from typing import Any

import pytest

from aura_python_sdk import (
    AuraClient,
    AuraResponseError,
    AuraValidationError,
    ConnectionMetrics,
    HealthStatus,
    HttpResponse,
    MetricNotFoundError,
    PrometheusMetric,
    PrometheusMetrics,
    ResourceMetrics,
    StorageMetrics,
)
from aura_python_sdk.services.prometheus import assess_health
from tests.fakes import FakeTransport, token_response
from tests.unit.conftest import INSTANCE_ID, Api

METRICS_URL = "https://customer-metrics-api.neo4j.io/api/v1/proj/2f49c2b3/metrics"

HEALTHY = """
# TYPE neo4j_aura_cpu_usage gauge
neo4j_aura_cpu_usage{instance_mode="PRIMARY"} 0.5
neo4j_aura_cpu_usage{instance_mode="SECONDARY"} 1.5
# TYPE neo4j_aura_cpu_limit gauge
neo4j_aura_cpu_limit 4
# TYPE neo4j_dbms_vm_heap_used_ratio gauge
neo4j_dbms_vm_heap_used_ratio 0.42
# TYPE neo4j_db_query_execution_success_total counter
neo4j_db_query_execution_success_total 1200
# TYPE neo4j_db_query_execution_internal_latency_q50 gauge
neo4j_db_query_execution_internal_latency_q50 3.5
# TYPE neo4j_dbms_bolt_connections_idle gauge
neo4j_dbms_bolt_connections_idle 10
# TYPE neo4j_dbms_bolt_connections_running gauge
neo4j_dbms_bolt_connections_running 5
# TYPE neo4j_dbms_bolt_connections_max_count gauge
neo4j_dbms_bolt_connections_max_count 100
# TYPE neo4j_dbms_page_cache_hit_ratio_per_minute gauge
neo4j_dbms_page_cache_hit_ratio_per_minute 0.98
"""


def _reply_text(api: Api, text: str) -> None:
    api.transport.queue(HttpResponse(200, {"Content-Type": "text/plain"}, text.encode()))


def _metrics(**samples: list[tuple[dict[str, str], float]]) -> PrometheusMetrics:
    return PrometheusMetrics(
        metrics={
            name: tuple(PrometheusMetric(name=name, labels=labels, value=v) for labels, v in values)
            for name, values in samples.items()
        }
    )


def test_fetch_raw_metrics_sends_token_to_metrics_url(api: Api) -> None:
    _reply_text(api, HEALTHY)
    metrics = api.client.prometheus.fetch_raw_metrics(METRICS_URL)
    assert len(metrics.metrics) == 9
    assert api.request.url == METRICS_URL
    assert api.request.headers["Authorization"].startswith("Bearer ")


@pytest.mark.parametrize(
    "url",
    [
        "http://customer-metrics-api.neo4j.io/metrics",
        "https://evil.example.com/metrics",
        "https://neo4j.io.evil.com/metrics",
        "https://evilneo4j.io/metrics",
        "ftp://customer-metrics-api.neo4j.io/metrics",
        "not a url",
        "",
    ],
)
def test_untrusted_urls_are_refused_before_sending_the_token(api: Api, url: str) -> None:
    with pytest.raises(AuraValidationError, match="prometheus URL"):
        api.client.prometheus.fetch_raw_metrics(url)
    api.assert_no_request()


def test_apex_domain_is_trusted(api: Api) -> None:
    _reply_text(api, "")
    api.client.prometheus.fetch_raw_metrics("https://neo4j.io/metrics")


def test_insecure_client_allows_local_metrics_urls() -> None:
    transport = FakeTransport([token_response(), HttpResponse(200, body=b"up 1")])
    client = AuraClient(
        client_id="id",
        client_secret="secret",
        base_url="http://localhost:9000",
        allow_insecure_base_url=True,
        transport=transport,
    )
    metrics = client.prometheus.fetch_raw_metrics("http://localhost:9100/metrics")
    assert metrics.metrics["up"][0].value == 1


def test_non_utf8_body(api: Api) -> None:
    api.transport.queue(HttpResponse(200, body=b"\xff\xfe"))
    with pytest.raises(AuraResponseError, match="UTF-8"):
        api.client.prometheus.fetch_raw_metrics(METRICS_URL)


def test_get_metric_value_averages_all_samples(api: Api) -> None:
    metrics = _metrics(cpu=[({"zone": "a"}, 1.0), ({"zone": "b"}, 3.0)])
    assert api.client.prometheus.get_metric_value(metrics, "cpu") == 2.0


def test_get_metric_value_with_label_filters(api: Api) -> None:
    metrics = _metrics(
        cpu=[
            ({"zone": "a", "mode": "PRIMARY"}, 1.0),
            ({"zone": "a", "mode": "SECONDARY"}, 5.0),
            ({"zone": "b", "mode": "PRIMARY"}, 3.0),
        ]
    )
    prometheus = api.client.prometheus
    assert prometheus.get_metric_value(metrics, "cpu", {"mode": "PRIMARY"}) == 2.0
    assert prometheus.get_metric_value(metrics, "cpu", {"zone": "a", "mode": "SECONDARY"}) == 5.0


def test_get_metric_value_not_found(api: Api) -> None:
    metrics = _metrics(cpu=[({"zone": "a"}, 1.0)])
    with pytest.raises(MetricNotFoundError, match="metric memory not found"):
        api.client.prometheus.get_metric_value(metrics, "memory")
    with pytest.raises(MetricNotFoundError, match="no matching metrics"):
        api.client.prometheus.get_metric_value(metrics, "cpu", {"zone": "z"})
    assert issubclass(MetricNotFoundError, LookupError)


def test_get_metric_value_requires_metrics(api: Api) -> None:
    with pytest.raises(AuraValidationError, match="PrometheusMetrics"):
        api.client.prometheus.get_metric_value({"cpu": []}, "cpu")  # type: ignore[arg-type]


def test_get_instance_health_healthy(api: Api) -> None:
    _reply_text(api, HEALTHY)
    health = api.client.prometheus.get_instance_health(INSTANCE_ID, METRICS_URL)

    assert health.instance_id == INSTANCE_ID
    assert health.overall_status is HealthStatus.HEALTHY
    assert health.resources.cpu_usage_percent == pytest.approx(25.0)  # mean 1.0 of 4 cores
    assert health.resources.memory_usage_percent == pytest.approx(42.0)
    assert health.query.query_execution_total == 1200
    assert health.query.avg_latency_ms == 3.5
    assert health.connections == ConnectionMetrics(
        active_connections=15, max_connections=100, usage_percent=15.0
    )
    assert health.storage.page_cache_hit_rate == pytest.approx(98.0)
    assert health.issues == ()
    assert health.recommendations == ()
    assert health.timestamp.tzinfo is not None


def test_get_instance_health_with_missing_metrics(
    api: Api, caplog: pytest.LogCaptureFixture
) -> None:
    _reply_text(api, "# TYPE neo4j_aura_cpu_usage gauge\nneo4j_aura_cpu_usage 3.9\n")
    health = api.client.prometheus.get_instance_health(INSTANCE_ID, METRICS_URL)
    assert health.resources.cpu_usage_percent is None  # no cpu_limit, so no percentage
    assert health.resources.memory_usage_percent is None
    assert health.connections == ConnectionMetrics()
    assert health.overall_status is HealthStatus.HEALTHY
    assert any("metric not available" in r.getMessage() for r in caplog.records)


def test_get_instance_health_validates_before_fetching(api: Api) -> None:
    with pytest.raises(AuraValidationError, match="instance ID"):
        api.client.prometheus.get_instance_health("bad", METRICS_URL)
    with pytest.raises(AuraValidationError, match="prometheus URL"):
        api.client.prometheus.get_instance_health(INSTANCE_ID, "https://example.com/metrics")
    api.assert_no_request()


def _assess(**kwargs: Any) -> tuple[HealthStatus, list[str], list[str]]:
    return assess_health(
        ResourceMetrics(
            cpu_usage_percent=kwargs.get("cpu"), memory_usage_percent=kwargs.get("memory")
        ),
        ConnectionMetrics(
            max_connections=kwargs.get("max_connections", 100), usage_percent=kwargs.get("conns")
        ),
        StorageMetrics(page_cache_hit_rate=kwargs.get("hit_rate")),
    )


@pytest.mark.parametrize(
    ("kwargs", "status", "issue"),
    [
        ({"cpu": 80.0}, HealthStatus.HEALTHY, None),
        ({"cpu": 80.1}, HealthStatus.WARNING, "High CPU usage: 80.1%"),
        ({"cpu": 95.5}, HealthStatus.CRITICAL, "Critical CPU usage: 95.5%"),
        ({"memory": 85.0}, HealthStatus.HEALTHY, None),
        ({"memory": 90.0}, HealthStatus.WARNING, "High memory usage: 90.0%"),
        ({"memory": 99.0}, HealthStatus.CRITICAL, "Critical memory usage: 99.0%"),
        ({"conns": 81.0}, HealthStatus.WARNING, "High connection usage: 81.0%"),
        ({"conns": 96.0}, HealthStatus.CRITICAL, "Critical connection usage: 96.0%"),
        ({"conns": 99.0, "max_connections": None}, HealthStatus.HEALTHY, None),
        ({"hit_rate": 50.0}, HealthStatus.HEALTHY, None),
        ({"hit_rate": 49.0}, HealthStatus.WARNING, "Low page cache hit rate: 49.0%"),
        ({"hit_rate": 10.0}, HealthStatus.CRITICAL, "Critical page cache hit rate: 10.0%"),
        ({"hit_rate": 0.0}, HealthStatus.HEALTHY, None),  # Go treats 0 as "no data"
    ],
)
def test_thresholds_match_go(
    kwargs: dict[str, Any], status: HealthStatus, issue: str | None
) -> None:
    result_status, issues, recommendations = _assess(**kwargs)
    assert result_status is status
    assert issues == ([] if issue is None else [issue])
    assert len(recommendations) == len(issues)


def test_critical_is_not_downgraded_by_a_later_warning() -> None:
    status, issues, _ = _assess(cpu=99.0, memory=90.0)
    assert status is HealthStatus.CRITICAL
    assert issues == ["Critical CPU usage: 99.0%", "High memory usage: 90.0%"]


def test_warning_is_upgraded_by_a_later_critical() -> None:
    status, _, _ = _assess(cpu=85.0, hit_rate=5.0)
    assert status is HealthStatus.CRITICAL


def test_critical_health_end_to_end(api: Api) -> None:
    _reply_text(
        api,
        HEALTHY.replace("neo4j_dbms_vm_heap_used_ratio 0.42", "neo4j_dbms_vm_heap_used_ratio 0.97"),
    )
    health = api.client.prometheus.get_instance_health(INSTANCE_ID, METRICS_URL)
    assert health.overall_status is HealthStatus.CRITICAL
    assert health.issues == ("Critical memory usage: 97.0%",)
    assert health.recommendations == ("Scale to a larger memory instance immediately",)
