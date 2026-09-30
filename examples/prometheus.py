"""Read an instance's Prometheus metrics and print a health summary.

Usage: python examples/prometheus.py INSTANCE_ID
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET, and metrics enabled for the instance in the Aura
Console.
"""

import sys

import aura_python_sdk as aura


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    instance_id = sys.argv[1]

    try:
        with aura.AuraClient.from_env() as client:
            url = client.instances.get(instance_id).metrics_integration_url
            if not url:
                print("metrics are not enabled for this instance", file=sys.stderr)
                return 1
            print(f"Metrics URL: {url}")

            metrics = client.prometheus.fetch_raw_metrics(url)
            names = sorted(metrics.metrics)
            print(f"\nFetched {len(names)} metrics, e.g.:")
            for name in names[:10]:
                print(f"  - {name}")

            try:
                nodes = client.prometheus.get_metric_value(metrics, "neo4j_database_count_node")
                print(f"\nNodes: {nodes:.0f}")
            except aura.MetricNotFoundError:
                print("\nNode count is not reported")

            health = client.prometheus.get_instance_health(instance_id, url)
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"\nOverall status: {health.overall_status} at {health.timestamp:%Y-%m-%d %H:%M:%S}")
    print(f"  CPU:            {percent(health.resources.cpu_usage_percent)}")
    print(f"  Memory (heap):  {percent(health.resources.memory_usage_percent)}")
    print(
        f"  Connections:    {health.connections.active_connections}/"
        f"{health.connections.max_connections} ({percent(health.connections.usage_percent)})"
    )
    print(f"  Page cache hit: {percent(health.storage.page_cache_hit_rate)}")
    for issue, recommendation in zip(health.issues, health.recommendations, strict=True):
        print(f"  ! {issue}: {recommendation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
