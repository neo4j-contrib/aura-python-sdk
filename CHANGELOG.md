# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The release workflow publishes
the `## vX.Y.Z` section that matches the pushed tag as the GitHub release notes.

## Unreleased

### Added

- `AsyncAuraClient` for asyncio. It has the same options and services as `AuraClient`, shares
  their validation and parsing, and uses an `AsyncHttpTransport` (httpx by default).
- `AuraClient` for the Aura API v1, with the Go SDK's options as keyword arguments, `from_env()`,
  and context-manager support.
- Services matching the Go SDK: `tenants`, `instances`, `snapshots`, `cmek`, `graph_analytics` and
  `prometheus`.
- Full v1 spec coverage beyond the Go SDK: `instances.estimate_size`, `instances.upgrade`,
  `cmek.get` / `create` / `delete`, list filters, and the `storage`, `vector_optimized` and
  `graph_analytics_plugin` update fields.
- Frozen dataclass models and `StrEnum`s that tolerate values the SDK doesn't know yet.
- An exception class per error: `NotFoundError`, `RateLimitError` (with `retry_after`) and others.
- A pluggable `HttpTransport`, with an httpx implementation as the default.
- Only network failures are retried, and a non-idempotent request is never re-sent once it may
  have reached the server.
- A stdlib Prometheus text-format parser whose output matches the Go SDK, and
  `get_instance_health` with the Go SDK's thresholds.

### Fixed

- `Instance.connection_url` is now optional. The live API returns `null` for some instances,
  although the spec marks the field as required, and that made `instances.get()` fail.
- `repr(HttpRequest)` no longer shows the bearer token or the Basic-auth client credentials, so
  a custom transport can log its requests safely. It now shows `***` for the `Authorization`
  value and only the body's length.

### Changed

- SDK errors now report their public name (for example `aura_python_sdk.NotFoundError`), and
  their tracebacks stop at the public method you called instead of listing the SDK's internal
  frames. Unexpected exceptions still show a full traceback.
- The live integration tests skip, instead of failing, when the credentials lack permission for
  an endpoint (HTTP 403).
- **Breaking:** the source of a copy is now a keyword-only argument, so a target and a source
  can't be swapped by accident: `overwrite_from_instance(instance_id, *, source_instance_id)`,
  `overwrite_from_snapshot(instance_id, *, source_snapshot_id)`,
  `create_from_instance(config, *, source_instance_id)` and
  `create_from_snapshot(config, *, source_instance_id, source_snapshot_id)`. `config` now comes
  first, as in `create(config)`.
- **Breaking:** list filters are keyword-only in every service: `instances.list(tenant_id=...)`,
  `cmek.list(tenant_id=...)` and `snapshots.list(instance_id, date=...)`.
- **Breaking:** `QueryMetrics.avg_latency_ms` is renamed `median_latency_ms`. It has always held
  the median (q50) query latency; the Go SDK's name for it is `AvgLatencyMs`.
