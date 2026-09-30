# Aura Python SDK — Plan

Scope: a Python client for **Aura API v1** (`aura_api_spec_v1 .yaml`), modelled on the v1 surface of
[aura-go-sdk](https://github.com/neo4j-contrib/aura-go-sdk) (root package only, not `v2beta1`).

Guiding rules:

- HTTP via **httpx** (no `requests`).
- **Every third-party import is wrapped.** Each dependency is imported by exactly one internal module,
  and no dependency type shows up in the public API. A test enforces this (see §6).
- Feel like the Go SDK: one client object, grouped services (`client.instances.list()`), the same
  layering (client → request service → HTTP service), the same validation and error semantics.
  Where Go idioms don't carry over (functional options, `ctx`, `(*T, error)` returns), use the
  Python equivalent.

---

## 1. Architecture (mirrors Go `docs/architecture.md`)

```
AuraClient                       public: config + grouped services
  ├── tenants / instances / snapshots / cmek / graph_analytics / prometheus
  ▼
RequestService (internal)        OAuth token cache + refresh, URL building (relative vs absolute),
                                 default headers, User-Agent, status → exception mapping
  ▼
HttpTransport (internal Protocol) send(HttpRequest) -> HttpResponse, retries, max response size
  ▼
HttpxTransport                   the ONLY module that imports httpx
```

The `HttpTransport` Protocol and its `HttpRequest`/`HttpResponse` dataclasses belong to us. That
covers "wrap every import": services and tests never touch httpx, and the Go `WithHTTPClient` option
becomes "pass your own `HttpTransport`" rather than "pass an `httpx.Client`".

## 2. Go → Python surface translation

### 2.1 Client construction

| Go | Python |
|---|---|
| `aura.NewClient(opts...)` | `AuraClient(client_id=..., client_secret=..., **options)` (keyword-only) |
| `WithCredentials(id, secret)` | `client_id=`, `client_secret=` (required, non-empty) |
| `WithTimeout(d)` (default 120s) | `timeout: float = 120.0` |
| `WithMaxRetry(n)` (default 3) | `max_retries: int = 3` |
| `WithLogger(*slog.Logger)` | `logger: logging.Logger \| None` (default `logging.getLogger("aura_python_sdk")` with a `NullHandler`) |
| `WithMaxResponseSize(n)` (10 MB) | `max_response_size: int = 10 * 1024 * 1024` |
| `WithBaseURL(url)` (https only) | `base_url: str = "https://api.neo4j.io"` (https enforced) |
| `WithInsecureBaseURL(url)` | `allow_insecure_base_url: bool = False` |
| `WithHTTPClient(*http.Client)` | `transport: HttpTransport \| None` (our Protocol, not httpx) |
| `WithUserAgent(ua)` | `user_agent: str` (default `aura-python-sdk/<version>`) |
| `WithDefaultHeaders(map)` | `default_headers: Mapping[str, str]` (Authorization / Content-Type / User-Agent silently dropped) |
| `defer client.Close()` | `client.close()` and `with AuraClient(...) as client:` |
| — | `AuraClient.from_env()` reading `AURA_CLIENT_ID` / `AURA_CLIENT_SECRET` (small addition) |

Invalid options raise `AuraConfigurationError` (a `ValueError`) from `__init__`, matching Go's
`NewClient` error return.

`context.Context` has no direct equivalent. The client-level `timeout` covers the per-call
`context.WithTimeout` that every Go method applies. We won't add a per-call timeout argument in v1.

### 2.2 Return values

Go returns wrapper structs (`*GetInstanceResponse{Data: InstanceData}`). The Python SDK **unwraps
`data`** and returns the model directly: `get()` returns an `Instance` and `list()` returns
`list[InstanceSummary]`. Nothing is lost, since v1 responses carry nothing but `data`.

### 2.3 Services

Each row is a Go method, followed by any spec endpoints it lacks (marked **new**).

**`client.tenants`** (`TenantService`)
| Python | HTTP |
|---|---|
| `list() -> list[TenantSummary]` | `GET /tenants` |
| `get(tenant_id) -> Tenant` | `GET /tenants/{id}` |
| `get_metrics_integration(tenant_id) -> MetricsIntegration` (Go: `GetMetrics`) | `GET /tenants/{id}/metrics-integration` |

**`client.instances`** (`InstanceService`)
| Python | HTTP |
|---|---|
| `list(tenant_id=None) -> list[InstanceSummary]` (`tenant_id` filter is **new**) | `GET /instances` |
| `get(instance_id) -> Instance` | `GET /instances/{id}` |
| `create(config: InstanceConfig) -> CreatedInstance` | `POST /instances` |
| `create_from_instance(source_instance_id, config)` | `POST /instances` + `source_instance_id` |
| `create_from_snapshot(source_instance_id, source_snapshot_id, config)` | `POST /instances` + both source IDs |
| `update(instance_id, *, name=, memory=, storage=, vector_optimized=, graph_analytics_plugin=, cdc_enrichment_mode=, secondaries_count=) -> Instance` | `PATCH /instances/{id}` (`storage`, `vector_optimized` and `graph_analytics_plugin` are **new**) |
| `delete(instance_id) -> Instance` | `DELETE /instances/{id}` |
| `pause(instance_id) -> Instance` | `POST /instances/{id}/pause` |
| `resume(instance_id) -> Instance` | `POST /instances/{id}/resume` |
| `overwrite_from_instance(instance_id, source_instance_id)` | `POST /instances/{id}/overwrite` |
| `overwrite_from_snapshot(instance_id, source_snapshot_id)` | `POST /instances/{id}/overwrite` |
| `estimate_size(node_count, relationship_count, *, instance_type=, algorithm_categories=) -> InstanceSizeEstimate` **new** | `POST /instances/sizing` |
| `upgrade(instance_id, *, memory=, storage=) -> Instance` **new** | `POST /instances/{id}/upgrade` |

`InstanceConfig` is a public dataclass, the equivalent of Go's `CreateInstanceConfigData`. It is
reused by the three `create*` methods and validated client-side with the same rules as Go's
`validateCreateInstanceConfig`.

**`client.snapshots`** (`SnapshotService`)
| Python | HTTP |
|---|---|
| `list(instance_id, date: datetime.date \| None = None) -> list[Snapshot]` (Go: `SnapshotDate`/`Today()`) | `GET /instances/{id}/snapshots?date=` |
| `get(instance_id, snapshot_id) -> Snapshot` | `GET /instances/{id}/snapshots/{sid}` |
| `create(instance_id) -> CreatedSnapshot` | `POST /instances/{id}/snapshots` |
| `restore(instance_id, snapshot_id) -> Instance` | `POST /instances/{id}/snapshots/{sid}/restore` |

**`client.cmek`** (`CMEKService`)
| Python | HTTP |
|---|---|
| `list(tenant_id=None) -> list[CustomerManagedKeySummary]` | `GET /customer-managed-keys` |
| `get(key_id) -> CustomerManagedKey` **new** | `GET /customer-managed-keys/{id}` |
| `create(*, name, key_id, region, cloud_provider, instance_type, tenant_id) -> CustomerManagedKey` **new** | `POST /customer-managed-keys` |
| `delete(key_id)` **new** | `DELETE /customer-managed-keys/{id}` |

**`client.graph_analytics`** (`GDSSessionService`)
| Python | HTTP |
|---|---|
| `list(*, tenant_id=None, instance_id=None, organization_id=None) -> list[GDSSession]` (filters are **new**) | `GET /graph-analytics/sessions` |
| `estimate_size(...) -> GDSSessionSizeEstimate` (Go: `Estimate`) | `POST /graph-analytics/sessions/sizing` |
| `create(config: GDSSessionConfig) -> GDSSession` | `POST /graph-analytics/sessions` |
| `get(session_id) -> GDSSession` | `GET /graph-analytics/sessions/{id}` |
| `delete(session_id) -> DeletedGDSSession` | `DELETE /graph-analytics/sessions/{id}` |

**`client.prometheus`** (`PrometheusService`, not a spec endpoint; calls the metrics URL with the Aura token)
| Python |
|---|
| `fetch_raw_metrics(prometheus_url) -> PrometheusMetrics` |
| `get_metric_value(metrics, name, label_filters=None) -> float` |
| `get_instance_health(instance_id, prometheus_url) -> InstanceHealth` (same metric names, thresholds and status logic as Go) |

### 2.4 Models

- Stdlib `@dataclass(frozen=True, slots=True)` with snake_case fields named after the JSON keys.
  The spec's names are used where Go renamed them (e.g. `graph_analytics_plugin`, not `GDSPlugin`).
- Timestamps become `datetime` and the snapshot date becomes `datetime.date`.
- Enums are `StrEnum`: `InstanceStatus`, `InstanceType`, `CloudProvider`, `CDCEnrichmentMode`,
  `GDSSessionStatus`. **Parsing is tolerant**: an unknown value from the API is kept as a plain `str`
  and does not raise, just as Go's string-typed fields tolerate it.
- Fields the API doesn't always return are `Optional` (e.g. `storage` on free instances, and
  `graph_nodes` / `secondaries_count`).
- Unknown JSON keys are ignored, so the SDK keeps working when the API adds fields.
- Secrets: `CreatedInstance.password` uses `field(repr=False)`, the equivalent of Go's redacting `String()`.
- The dict↔dataclass conversion lives in one internal `_serde` module. No pydantic (see §7).

### 2.5 Errors

Go has one `*aura.Error` with `IsNotFound()` / `IsUnauthorized()` / `IsBadRequest()`, `AllErrors()`
and `HasMultipleErrors()`. In Python that becomes an exception hierarchy:

```
AuraError
├── AuraConfigurationError (also ValueError)   bad client options
├── AuraValidationError   (also ValueError)   bad IDs / args, raised before any HTTP call
├── AuraConnectionError                        network failure after retries
│   └── AuraTimeoutError
├── AuraResponseError                          body too large, or JSON / type mismatch
└── AuraAPIError  (.status_code, .message, .details: list[ErrorDetail], .request_id)
    ├── BadRequestError        400
    ├── AuthenticationError    401 (also raised when fetching the token fails)
    ├── PermissionDeniedError  403
    ├── NotFoundError          404
    ├── ConflictError          409
    ├── RateLimitError         429 (.retry_after)
    └── ServerError            5xx
```

`AuraAPIError` keeps Go's convenience API (`is_not_found`, `all_errors()`, `has_multiple_errors`)
and its message format (`API error (status 404): ... - detail (and N more error(s))`). The error
parser accepts the spec's `{"errors": [...]}`, the middleware `{"error": "..."}` shape, and Go's
`message` / `details`.

### 2.6 Cross-cutting behaviour carried over from Go

- ID validation before any request: instance ID is 8 hex characters; tenant and snapshot IDs are
  UUIDs; GDS session IDs must be non-empty.
- Token management: client-credentials `POST {base_url}/oauth/token` with Basic auth. Tokens are
  cached, refreshed 60 s before expiry, and the refresh is thread-safe (`threading.Lock`). The token
  type must be `Bearer` and `expires_in` must fall in a sane range.
- Retries only on network errors: up to `max_retries`, with 1–5 s backoff. Responses with an HTTP
  status (4xx or 5xx) are never retried, matching Go's `networkOnlyRetryPolicy`.
- The response body is capped at `max_response_size`.
- TLS 1.2 minimum. Relative paths get `{base_url}/v1/` prepended; absolute URLs (Prometheus) pass
  through unchanged.
- Logging goes to the stdlib `logging` module, at debug level for requests and info level for
  mutations. Credentials, tokens and passwords are never logged.

### 2.7 Deliberate differences from Go (decided in phase 2)

- **Retry safety.** Go retries every network error for every method. Here, if the request may have
  reached the server (read timeout, connection reset), only idempotent methods (GET, PUT, DELETE,
  HEAD, OPTIONS) are retried. This stops a `POST /instances` from being sent twice and creating a
  duplicate billable instance. Errors that happen before anything is sent (connect errors, pool
  timeouts) are retried for every method. Transports report which case applies through
  `AuraConnectionError.request_sent`.
- **One deadline per call.** `timeout` covers the token fetch, every attempt and every backoff,
  matching Go's `context.WithTimeout` per method. A retry is skipped if its backoff would pass the
  deadline.
- **`max_retries=0` is allowed** and means a single attempt. Go requires at least 1.
- **A 401 clears the cached token**, so the next call fetches a new one. The failed call is not
  retried.
- **Token endpoint errors.** Any 4xx from `/oauth/token` raises `AuthenticationError`; 429 and 5xx
  keep their usual types. A lower-case `bearer` token type is accepted.
- **Transport ownership.** `close()` closes only a transport the client created itself.

### 2.8 Decisions made in phase 5

- **Names**: instance and CMEK names must be 1–30 characters with no leading or trailing
  whitespace, as the spec states. Go checks only length, and only on create.
- **CMEK IDs**: `get` and `delete` only require a non-empty key ID, which is then path-encoded.
  The spec doesn't say whether these IDs are UUIDs.
- **`upgrade()`**: `memory` and `storage` must be given together or not at all, as the spec
  requires. With neither, it sends `{}`.
- **`cmek.delete()`** returns `None`, since the API responds 204 with no body.
- **Coverage guard**: `test_every_spec_operation_has_a_client_method` fails if the spec gains an
  operation that no SDK method covers.

### 2.9 Decisions made in phase 6

- **No `prometheus_client`.** It normalises counter names (`foo` becomes `foo_total`) and
  converts timestamps to seconds, so its keys wouldn't match the Go SDK's. A roughly 150-line
  stdlib parser gives exactly the same output as Go's `expfmt`, checked with a Go program on the
  same input. The `[prometheus]` extra is gone, so httpx is the only runtime dependency.
- **Metrics URL guard.** The Aura bearer token is sent to the metrics URL, so it must be
  `https://*.neo4j.io` unless `allow_insecure_base_url=True`. Go sends the token to any URL.
- **Missing metrics are `None`, not `0`.** `InstanceHealth` fields are `None` when the endpoint
  didn't report a metric, and threshold checks skip them. The status logic and messages match Go.
- **`get_metric_value`** raises `MetricNotFoundError`, which is also a `LookupError`.

### 2.10 Decisions made in phase 8 (async)

- **Written once, run two ways.** Each service operation is a pure function that validates its
  arguments and returns a `Call` (method, path, params, body, parser, log text). `Service._run`
  sends it synchronously and `AsyncService._run` awaits it. The retry policy, token parsing,
  header building and error mapping are shared the same way, and only the I/O loops are
  duplicated.
- **Thin async classes.** `AsyncInstanceService` and the other async services repeat only the
  signatures, and their docstrings point to the sync methods.
- **Parity is enforced.** `tests/unit/test_async_parity.py` runs every method on both clients
  against the same responses and asserts identical requests and results. It also checks the
  signatures match, and fails if a method has no case. Two deliberately broken methods were
  caught.
- **Transports can't be mixed up.** `AuraClient` rejects a transport whose `send` is a coroutine,
  and `AsyncAuraClient` requires one. mypy catches the same mistake statically.
- **`asyncio.Lock`** guards the token refresh, so concurrent tasks share one token fetch.
- **Test tooling:** async tests use anyio's pytest plugin, which is already installed with httpx.
  No new dependency.

## 3. Package layout

```
pyproject.toml                 # hatchling, dist aura-python-sdk, requires-python >=3.11
src/aura_python_sdk/
  __init__.py                  # public exports + __all__
  py.typed
  _client.py                   # AuraClient
  _config.py                   # option defaults + validation
  _errors.py
  _version.py                  # importlib.metadata
  _validation.py               # ID / input validators
  models/                      # tenants.py, instances.py, snapshots.py, cmek.py, graph_analytics.py, prometheus.py
  services/                    # same split; each service takes a RequestService
  _internal/
    _serde.py                  # JSON <-> dataclass
    _auth.py                   # TokenManager
    _request.py                # RequestService
    http/
      _types.py                # HttpRequest, HttpResponse, HttpTransport Protocol
      _httpx.py                # HttpxTransport, the only httpx import
    metrics/
      _parser.py               # stdlib Prometheus text-format parser (matches Go expfmt)
tests/
  unit/                        # FakeTransport, no network
  transport/                   # HttpxTransport against httpx.MockTransport
  integration/                 # opt-in real Aura, skipped unless env vars are set
examples/                      # ports of go examples/v1/*
```

## 4. Dependencies

| Dependency | Purpose | Wrapped in |
|---|---|---|
| `httpx` | HTTP | `_internal/http/_httpx.py` |

Dev tooling: `uv`, `ruff` (lint and format), `mypy --strict`, `pytest`, `pytest-cov`. No `respx`:
`httpx.MockTransport` plus our own fake transport are enough.

## 5. Phases

**Status:** all eight phases are done.

1. **Scaffold**: pyproject, uv, ruff, mypy, pytest config, CI workflow, and the import-boundary test.
2. **Core**: config/options, errors, `HttpTransport` + `HttpxTransport` (retries, size cap),
   `TokenManager`, `RequestService`, and `AuraClient` with no services yet. Unit-tested to Go's
   coverage (token refresh, header filtering, error parsing, URL handling).
3. **Models + serde**: all v1 models and enums with tolerant parsing, tested against the spec's
   example payloads.
4. **Services at Go parity**: tenants, instances, snapshots, `cmek.list`, graph_analytics.
5. **Spec gap-fill**: instance sizing and upgrade, CMEK get/create/delete, list filters, extra PATCH fields.
6. **Prometheus**: a stdlib metrics parser plus the health assessment.
7. **Docs and release**: README, the ported examples, CHANGELOG, opt-in integration tests, PyPI publish workflow.
8. *(If chosen)* **Async**: `AsyncAuraClient` over an `AsyncHttpTransport`, reusing request
   building and parsing. The layering keeps this additive.

## 6. Enforcing "wrap every import"

A unit test walks `src/` with `ast` and fails if `httpx` (or any unregistered dependency) is imported anywhere
except its designated module. It also checks that no public symbol's annotations reference those
packages.

## 7. Decisions (confirmed)

1. **Names**: distribution `aura-python-sdk`, to match `aura-go-sdk`. The import name is
   `aura_python_sdk` (a hyphen isn't valid in an import). Users can write
   `import aura_python_sdk as aura` to get the Go-style `aura.` prefix.
2. **Sync first.** Async comes later, as phase 8.
3. **Scope**: the full v1 spec, including phase 5.
4. **Models**: stdlib dataclasses.
5. **Python**: 3.11 minimum.

## 8. Spec and Go discrepancies to resolve during implementation

- **Query parameter name**: the spec names the list-filter parameter `tenantId`, but Go sends
  `tenant_id` (CMEK list). *Resolved: follow the spec. `tenantId` is used for
  every list filter (defined once in `services/cmek.py`).*
- **Overwrite response**: Go models it as `{"data": "<job id string>"}`, but the spec says
  `Instance`. The Go tests only use mocks. *Resolved: follow the spec. `overwrite_from_instance`
  and `overwrite_from_snapshot` return `Instance`.*
- **GDS `ttl` type**: the spec says `integer` in the session details but `string` in the create
  request. Go uses string throughout.
- **GDS create response**: the spec has an odd `data: {type: object, items: ...}` shape. Treat it as
  a single session, as Go does.
- **PATCH fields**: `secondaries_count` and `cdc_enrichment_mode` appear only in the spec's examples,
  not its schema. Go sends them, so we keep them.
- **Instance status `stopped` / `available`**: present in Go but not in the spec enum. Keep them for
  parity; tolerant parsing makes this harmless.
- **Snapshot ID format**: resolved. Snapshot IDs are UUIDs, and the spec's list example
  (`snapshot_id: '2023-01-20T13:44:42Z'`) is wrong. We keep Go's UUID validation.
- **`connection_url` can be null**: the first live run showed that `GET /instances/{id}`
  returns `connection_url: null` for some instances, although the spec marks it as required.
  `Instance.connection_url` is now optional. Run the live tests again after spec updates, to
  catch fields that are required in the spec but missing in practice.
- **Required fields on responses**: models follow the spec's `required` lists, with two
  exceptions. Instance `storage` is optional because it isn't returned for Free instances. GDS
  session `status` is optional because the spec's 202 example returns `null`. A missing required
  field raises `AuraResponseError` and names the field.
