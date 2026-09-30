"""``client.prometheus`` (Go: PrometheusService)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit

from aura_python_sdk import _validation as validate
from aura_python_sdk._errors import AuraResponseError, AuraValidationError, MetricNotFoundError
from aura_python_sdk._internal._call import Call
from aura_python_sdk._internal._request import ApiResponse, AsyncRequestService, RequestService
from aura_python_sdk._internal.metrics._parser import parse_exposition
from aura_python_sdk.models.prometheus import (
    ConnectionMetrics,
    HealthStatus,
    InstanceHealth,
    PrometheusMetrics,
    QueryMetrics,
    ResourceMetrics,
    StorageMetrics,
)
from aura_python_sdk.services._base import AsyncService, Service

# The Aura bearer token is sent with every metrics request, so by default only Aura's own
# metrics hosts are allowed.
_TRUSTED_METRICS_DOMAIN = "neo4j.io"

# --- Operations and pure helpers (no I/O) ---


def _check_url(prometheus_url: str, *, allow_untrusted: bool) -> str:
    url = validate.require_non_empty("prometheus URL", prometheus_url)
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise AuraValidationError(f"prometheus URL is not a valid http(s) URL: {url!r}")
    if allow_untrusted:
        return url
    host = parts.hostname.lower()
    trusted = host == _TRUSTED_METRICS_DOMAIN or host.endswith(f".{_TRUSTED_METRICS_DOMAIN}")
    if parts.scheme != "https" or not trusted:
        raise AuraValidationError(
            f"prometheus URL must be an https://*.{_TRUSTED_METRICS_DOMAIN} address, because "
            "the Aura API token is sent with the request"
        )
    return url


def _parse_metrics(response: ApiResponse) -> PrometheusMetrics:
    try:
        text = response.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuraResponseError("metrics response is not valid UTF-8") from exc
    return PrometheusMetrics(metrics=parse_exposition(text))


def _fetch(prometheus_url: str, *, allow_untrusted: bool) -> Call[PrometheusMetrics]:
    url = _check_url(prometheus_url, allow_untrusted=allow_untrusted)
    return Call(
        method="GET",
        path=url,
        parse=_parse_metrics,
        describe="fetching Prometheus metrics",
        context={"url": url},
    )


def metric_value(
    metrics: PrometheusMetrics, name: str, label_filters: Mapping[str, str] | None = None
) -> float:
    """The mean value of ``name`` across samples matching ``label_filters`` (Go semantics)."""
    if not isinstance(metrics, PrometheusMetrics):
        raise AuraValidationError("metrics must be a PrometheusMetrics")
    samples = metrics.metrics.get(name)
    if not samples:
        raise MetricNotFoundError(f"metric {name} not found")
    filters = dict(label_filters or {})
    matching = [s for s in samples if all(s.labels.get(k) == v for k, v in filters.items())]
    if not matching:
        raise MetricNotFoundError(f"no matching metrics found for {name} with filters {filters}")
    return sum(s.value for s in matching) / len(matching)


def build_health(
    instance_id: str, metrics: PrometheusMetrics, logger: logging.Logger
) -> InstanceHealth:
    """Build the health summary from fetched metrics, using the Go SDK's metric names."""

    def value(name: str) -> float | None:
        try:
            return metric_value(metrics, name)
        except MetricNotFoundError:
            logger.warning("metric not available", extra={"metric": name})
            return None

    cpu_usage = value("neo4j_aura_cpu_usage")
    cpu_limit = value("neo4j_aura_cpu_limit") if cpu_usage is not None else None
    heap_ratio = value("neo4j_dbms_vm_heap_used_ratio")
    resources = ResourceMetrics(
        cpu_usage_percent=(
            cpu_usage / cpu_limit * 100
            if cpu_usage is not None and cpu_limit and cpu_limit > 0
            else None
        ),
        memory_usage_percent=heap_ratio * 100 if heap_ratio is not None else None,
    )

    query = QueryMetrics(
        query_execution_total=value("neo4j_db_query_execution_success_total"),
        median_latency_ms=value("neo4j_db_query_execution_internal_latency_q50"),
    )

    idle = value("neo4j_dbms_bolt_connections_idle")
    running = value("neo4j_dbms_bolt_connections_running")
    max_connections = value("neo4j_dbms_bolt_connections_max_count")
    active = int(idle + running) if idle is not None and running is not None else None
    connections = ConnectionMetrics(
        active_connections=active,
        max_connections=int(max_connections) if max_connections and max_connections > 0 else None,
        usage_percent=(
            active / max_connections * 100
            if active is not None and max_connections and max_connections > 0
            else None
        ),
    )

    hit_ratio = value("neo4j_dbms_page_cache_hit_ratio_per_minute")
    storage = StorageMetrics(page_cache_hit_rate=hit_ratio * 100 if hit_ratio is not None else None)

    status, issues, recommendations = assess_health(resources, connections, storage)
    logger.info("instance health assessed", extra={"instance_id": instance_id, "status": status})
    return InstanceHealth(
        instance_id=instance_id,
        timestamp=datetime.now(UTC),
        resources=resources,
        query=query,
        connections=connections,
        storage=storage,
        overall_status=status,
        issues=tuple(issues),
        recommendations=tuple(recommendations),
    )


# --- Services ---


class PrometheusService(Service):
    """Aura's Prometheus metrics endpoints.

    Get an endpoint from ``client.tenants.get_metrics_integration(tenant_id).endpoint`` or
    ``client.instances.get(instance_id).metrics_integration_url``.
    """

    def __init__(
        self, api: RequestService, logger: logging.Logger, *, allow_untrusted_urls: bool = False
    ) -> None:
        super().__init__(api, logger)
        self._allow_untrusted_urls = allow_untrusted_urls

    def fetch_raw_metrics(self, prometheus_url: str) -> PrometheusMetrics:
        """Fetch and parse every metric from a metrics endpoint."""
        return self._run(_fetch(prometheus_url, allow_untrusted=self._allow_untrusted_urls))

    def get_metric_value(
        self,
        metrics: PrometheusMetrics,
        name: str,
        label_filters: Mapping[str, str] | None = None,
    ) -> float:
        """The mean value of ``name`` across every sample whose labels match ``label_filters``.

        Raises :class:`MetricNotFoundError` if nothing matches.
        """
        return metric_value(metrics, name, label_filters)

    def get_instance_health(self, instance_id: str, prometheus_url: str) -> InstanceHealth:
        """Summarise an instance's CPU, memory, query, connection and page cache metrics.

        Uses the same metrics, thresholds and status logic as the Go SDK.
        """
        instance_id = validate.instance_id(instance_id)
        call = _fetch(prometheus_url, allow_untrusted=self._allow_untrusted_urls)
        return build_health(instance_id, self._run(call), self._logger)


class AsyncPrometheusService(AsyncService):
    """Async version of :class:`PrometheusService`, with the same arguments and behaviour.

    ``get_metric_value`` does no I/O, so it is a plain (non-async) method here too.
    """

    def __init__(
        self,
        api: AsyncRequestService,
        logger: logging.Logger,
        *,
        allow_untrusted_urls: bool = False,
    ) -> None:
        super().__init__(api, logger)
        self._allow_untrusted_urls = allow_untrusted_urls

    async def fetch_raw_metrics(self, prometheus_url: str) -> PrometheusMetrics:
        """See :meth:`PrometheusService.fetch_raw_metrics`."""
        return await self._run(_fetch(prometheus_url, allow_untrusted=self._allow_untrusted_urls))

    def get_metric_value(
        self,
        metrics: PrometheusMetrics,
        name: str,
        label_filters: Mapping[str, str] | None = None,
    ) -> float:
        """See :meth:`PrometheusService.get_metric_value`."""
        return metric_value(metrics, name, label_filters)

    async def get_instance_health(self, instance_id: str, prometheus_url: str) -> InstanceHealth:
        """See :meth:`PrometheusService.get_instance_health`."""
        instance_id = validate.instance_id(instance_id)
        call = _fetch(prometheus_url, allow_untrusted=self._allow_untrusted_urls)
        return build_health(instance_id, await self._run(call), self._logger)


def assess_health(
    resources: ResourceMetrics, connections: ConnectionMetrics, storage: StorageMetrics
) -> tuple[HealthStatus, list[str], list[str]]:
    """Apply the Go SDK's thresholds. Returns (status, issues, recommendations)."""
    status = HealthStatus.HEALTHY
    issues: list[str] = []
    recommendations: list[str] = []

    def flag(level: HealthStatus, issue: str, recommendation: str) -> None:
        nonlocal status
        issues.append(issue)
        recommendations.append(recommendation)
        if level is HealthStatus.CRITICAL or status is HealthStatus.HEALTHY:
            status = level

    cpu = resources.cpu_usage_percent
    if cpu is not None:
        if cpu > 95:
            flag(
                HealthStatus.CRITICAL,
                f"Critical CPU usage: {cpu:.1f}%",
                "Scale to a larger instance size immediately",
            )
        elif cpu > 80:
            flag(
                HealthStatus.WARNING,
                f"High CPU usage: {cpu:.1f}%",
                "Consider scaling to a larger instance size",
            )

    memory = resources.memory_usage_percent
    if memory is not None:
        if memory > 95:
            flag(
                HealthStatus.CRITICAL,
                f"Critical memory usage: {memory:.1f}%",
                "Scale to a larger memory instance immediately",
            )
        elif memory > 85:
            flag(
                HealthStatus.WARNING,
                f"High memory usage: {memory:.1f}%",
                "Consider scaling to a larger memory instance",
            )

    usage = connections.usage_percent
    if usage is not None and connections.max_connections:
        if usage > 95:
            flag(
                HealthStatus.CRITICAL,
                f"Critical connection usage: {usage:.1f}%",
                "Reduce active connections immediately; review connection pooling",
            )
        elif usage > 80:
            flag(
                HealthStatus.WARNING,
                f"High connection usage: {usage:.1f}%",
                "Review connection pooling configuration in your application",
            )

    hit_rate = storage.page_cache_hit_rate
    # As in Go, a hit rate of exactly 0 is treated as "no data".
    if hit_rate:
        if hit_rate < 20:
            flag(
                HealthStatus.CRITICAL,
                f"Critical page cache hit rate: {hit_rate:.1f}%",
                "Increase page cache size immediately; query performance is severely degraded",
            )
        elif hit_rate < 50:
            flag(
                HealthStatus.WARNING,
                f"Low page cache hit rate: {hit_rate:.1f}%",
                "Consider increasing page cache size for better performance",
            )

    return status, issues, recommendations
