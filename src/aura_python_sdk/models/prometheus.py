"""Prometheus metrics models (Go: prometheus.go)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from aura_python_sdk._errors import MetricNotFoundError


@dataclass(frozen=True, slots=True, kw_only=True)
class PrometheusMetric:
    """One sample. For summaries and histograms, ``value`` is the ``_sum`` sample, as in Go."""

    name: str
    labels: Mapping[str, str] = field(default_factory=dict)
    value: float
    timestamp_ms: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PrometheusMetrics:
    """Every sample from a metrics endpoint, keyed by metric name.

    A counter is keyed by the name on its ``# TYPE`` line (for example
    ``neo4j_db_query_execution_success_total``). A summary or histogram is keyed by its base name.
    """

    metrics: Mapping[str, tuple[PrometheusMetric, ...]] = field(default_factory=dict)

    def value(self, name: str, /, **labels: str) -> float:
        """The mean value of ``name`` across every sample with these label values.

        ::

            metrics.value("neo4j_aura_cpu_usage", instance_mode="PRIMARY")

        Raises:
            MetricNotFoundError: No sample of ``name`` has these labels.
        """
        samples = self.metrics.get(name)
        if not samples:
            raise MetricNotFoundError(f"metric {name} not found")
        matching = [s for s in samples if all(s.labels.get(k) == v for k, v in labels.items())]
        if not matching:
            raise MetricNotFoundError(f"no matching metrics found for {name} with filters {labels}")
        return sum(s.value for s in matching) / len(matching)


class HealthStatus(StrEnum):
    """The overall health in an :class:`InstanceHealth`: healthy, warning or critical."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceMetrics:
    """CPU and heap memory use, as percentages of the instance's limits."""

    cpu_usage_percent: float | None = None
    memory_usage_percent: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryMetrics:
    """Query counts and latency, in milliseconds."""

    query_execution_total: float | None = None
    # The median (q50) internal query latency. The Go SDK calls this AvgLatencyMs.
    median_latency_ms: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionMetrics:
    """Bolt connections in use, against the instance's limit."""

    active_connections: int | None = None
    max_connections: int | None = None
    usage_percent: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageMetrics:
    """Page cache effectiveness: the hit rate as a percentage."""

    page_cache_hit_rate: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class InstanceHealth:
    """A health summary built from an instance's metrics (Go: ``PrometheusHealthMetrics``).

    A value is ``None`` when the endpoint didn't report the metric. Go reports ``0`` in that
    case.
    """

    instance_id: str
    timestamp: datetime
    resources: ResourceMetrics
    query: QueryMetrics
    connections: ConnectionMetrics
    storage: StorageMetrics
    overall_status: HealthStatus
    issues: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
