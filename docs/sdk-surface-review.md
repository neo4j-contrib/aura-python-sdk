# aura-python-sdk public API review

**Scope:** branch `release-automation` at `6963b50`. Every finding now has a **Status** line;
the fixes are on branch `api-review-fixes`. This covers the public surface exported from
`aura_python_sdk/__init__.py`, `aura_python_sdk.models` and `aura_python_sdk.services`.

**Summary:** The SDK is in good shape. Clients are keyword-only and validated when they're
built, there's one exception hierarchy, models cope with API changes, and the sync and async
clients match exactly. Four things are worth fixing before 1.0 because fixing them later
breaks callers:
- Destructive methods take two instance IDs positionally, so they're easy to swap (#1).
- Filter arguments are positional in some services and keyword-only in others (#2).
- The public `HttpRequest` type prints bearer tokens in its `repr` (#3).
- A metric field called "avg" actually holds the median (#4).

Findings #3, #5, #6 and #7 were confirmed by running code. The rest were checked by reading it.

## Must fix

### 1. Destructive methods take two positional IDs of the same type
**Status:** Fixed in `a8b1a39`. The source IDs are keyword-only, and `config` comes first in `create_from_*`.

**Where:** `src/aura_python_sdk/services/instances.py:342` (`overwrite_from_instance`), `:346`
(`overwrite_from_snapshot`), `:257` (`create_from_instance`), `:263` (`create_from_snapshot`),
and the async versions at `:366`, `:372`, `:435` and `:439`.

**Problem:** the target and the source are both plain `str` arguments, so type checking can't
catch them swapped:
```python
client.instances.overwrite_from_instance("prod1234", "test1234")  # which way round is it?
```
Swapping them overwrites the *wrong* instance, which is permanent data loss. mypy passes both
orders. `create_from_instance(source_instance_id, config)` also puts the source first, which is
the opposite of the `overwrite_*` methods.

**Why it matters:** the Azure SDK guidelines and the checklist both say: required identifiers
can be positional, everything else keyword-only. When two arguments have the same type and
different meanings, and swapping them destroys data, naming them should be compulsory.

**Suggested fix:** make the source keyword-only:
`overwrite_from_instance(instance_id, *, source_instance_id)` and
`create_from_snapshot(config, *, source_instance_id, source_snapshot_id)`. This is breaking,
so do it before 1.0.

### 2. List filters are positional in some services and keyword-only in others
**Status:** Fixed in `a8b1a39`.

**Where:** `services/instances.py:241` `list(tenant_id=None)`, `services/cmek.py`
`list(tenant_id=None)` and `services/snapshots.py` `list(instance_id, date=None)` are
positional. `services/graph_analytics.py` `list(*, tenant_id, instance_id, organization_id)`
is keyword-only.

**Problem:** `client.instances.list("t-123")` works, but the same call on
`graph_analytics.list` raises `TypeError`. If more filters are added to `instances.list`
later, the existing positional filter can't move without breaking callers.

**Why it matters:** filters are optional settings, not identifiers. The README already writes
`list(tenant_id=...)`, which suggests keyword-only was the intent.

**Suggested fix:** put `*` before every optional filter (`list(self, *, tenant_id=None)`,
`snapshots.list(instance_id, *, date=None)`). Only callers passing filters positionally are
affected, so do it before 1.0.

### 3. `HttpRequest.__repr__` shows the bearer token and the client secret
**Status:** Fixed in `378f925`. The `repr` shows `***` for `Authorization` and only the body's length.

**Where:** `src/aura_python_sdk/_transport.py:16-30`. The OAuth request built in
`_internal/_auth.py:52-56` carries `Authorization: Basic base64(client_id:client_secret)`
through the same type.

**Problem:** `HttpRequest` is a public type that custom transports receive, and its default
dataclass `repr` includes `headers`:
```python
class LoggingTransport:
    def send(self, request):
        log.debug("sending %r", request)  # writes "Authorization: Bearer eyJ..." to logs
```
Confirmed: `"SECRET" in repr(HttpRequest(headers={"Authorization": "Bearer SECRET"}, ...))`
is `True`. Logging the request is the first thing anyone writing a transport or debugging a
proxy will do. The SDK's own logs are careful, and `ClientConfig.client_secret` and
`CreatedInstance.password` both use `repr=False`, so this is the one gap.

**Suggested fix:** use `headers: Mapping[str, str] = field(repr=False)`, or a custom `__repr__`
that shows header names and replaces `Authorization` with `***`. This isn't breaking.

### 4. `QueryMetrics.avg_latency_ms` holds the median
**Status:** Fixed in `0a1cd6e`. Renamed `median_latency_ms` with no alias (a clean break before 1.0). The README's Go table maps the old name.

**Where:** `src/aura_python_sdk/models/prometheus.py:48`

**Problem:** the field is populated from the q50 quantile. The comment says this matches the Go
SDK's naming. Callers who read the name and don't see the comment will treat a median as a
mean in dashboards and alerts, and the two can be far apart for query latency.

**Why it matters:** a public field name is a promise about its meaning, and renaming it later
is breaking. Matching Go's names is a good default, but not where Go's name is wrong.

**Suggested fix:** rename it to `median_latency_ms` (or `p50_latency_ms`). If you want to keep
Go compatibility for a while, keep `avg_latency_ms` as a deprecated alias property.

## Should fix

### 5. `from_env(**options: object)` switches off type checking for every option
**Status:** Fixed in `7eba703`, using `Unpack` with private `TypedDict`s. A test keeps them in step with `__init__`.

**Where:** `src/aura_python_sdk/_client.py:178` and `:304` (both need `# type: ignore[arg-type]`)

**Problem:** confirmed with `mypy --strict` on a caller's script:
`AuraClient.from_env(timout=5)` passes type checking and fails only when it runs. The same
goes for a wrongly typed `timeout="5"`. `from_env` is the documented way to build a client, so
this affects most callers.

**Suggested fix:** define a `ClientOptions(TypedDict, total=False)` with the options and use
`**options: Unpack[ClientOptions]` (PEP 692; `typing.Unpack` exists in 3.11). Alternatively,
repeat the keyword parameters explicitly. This isn't breaking.

### 6. A closed client raises httpx's `RuntimeError`
**Status:** Fixed in `ed09f45`. Adds `AuraClientClosedError(AuraError, RuntimeError)`.

**Where:** `src/aura_python_sdk/_client.py:190` sets `_closed`, but nothing checks it.

**Problem:** confirmed. Calling `client.tenants.list()` after `close()` raises
`builtins.RuntimeError: Cannot send a request, as the client has been closed.` That exception
comes from httpx, so `except AuraError` misses it, and httpx leaks through the one boundary the
SDK otherwise keeps (`_httpx.py` wraps only `httpx.TransportError`).

**Suggested fix:** check `_closed` before sending and raise an SDK error that makes sense
here. A new `AuraClientClosedError(AuraError, RuntimeError)` keeps compatibility with anyone
catching `RuntimeError`. The async client needs the same change.

### 7. SDK exceptions can't be pickled
**Status:** Fixed in `b612765`. A test pickles every exported exception.

**Where:** `src/aura_python_sdk/_errors.py:37` (`AuraConnectionError`), `:66`
(`AuraAPIError`) and `:132` (`RateLimitError`)

**Problem:** confirmed. `pickle.loads(pickle.dumps(NotFoundError(404, "nope")))` raises
`TypeError: missing 1 required positional argument: 'message'`, and `AuraConnectionError`
fails on `request_sent`. Anything that sends exceptions between processes breaks:
`concurrent.futures.ProcessPoolExecutor`, `multiprocessing`, Celery and Dask. The caller then
gets a confusing `TypeError` in place of the real API error.

**Suggested fix:** add a `__reduce__` to `AuraAPIError` and `AuraConnectionError` that rebuilds
the exception from its attributes, and add a pickling test for each exported exception. This
isn't breaking.

### 8. There's no helper for waiting on long-running operations
**Status:** Fixed in `9a89e17`. Added `instances.wait_for_status()`, `snapshots.wait_for_completion()` and `graph_analytics.wait_until_ready()`, plus `OperationFailedError` and `WaitTimeoutError`. A 404 in the first minute is retried. `wait_for_status()` can't detect the end of an update, upgrade, overwrite or restore, and says so.

**Where:** `services/instances.py` (`create`, `pause`, `resume`, `update`, `upgrade`,
`overwrite_*`), `services/snapshots.py` (`create`, `restore`), and the README at line 176
("poll `get()` until the status is `running`").

**Problem:** almost every change in this API is asynchronous, so every caller writes the same
polling loop and has to decide how often to poll, what to do about failed states
(`loading failed`, snapshot `Failed`) and when to give up. Hand-written loops often poll too
often or never time out.

**Suggested fix:** add
`instances.wait_for_status(instance_id, status=InstanceStatus.RUNNING, *, timeout=..., interval=...)`
(and a snapshot version) that raises a timeout error and stops early on a failed state. This
is a new API, so it isn't breaking.

### 9. There's no statement of what's stable
**Status:** Fixed in `567618d`. The README has a Versioning section.

**Where:** the README and CHANGELOG. The classifier is `Development Status :: 3 - Alpha`.

**Problem:** callers can't tell which names are public (is `aura_python_sdk.services` public?
is `HttpxTransport`?) or whether 0.x minor releases may break them. That matters more now that
you're publishing to TestPyPI.

**Suggested fix:** add a short "Versioning" section to the README:
- The public API is what's exported from `aura_python_sdk`, `aura_python_sdk.models` and
  `aura_python_sdk.services`. Anything with a leading underscore is private.
- It follows SemVer from 1.0. Before 1.0, minor releases may break and are recorded in the
  CHANGELOG.
- Deprecations use `DeprecationWarning`.

### 10. Docstrings have summaries but no parameters, return values or exceptions
**Status:** Fixed in `90ffa17`. Method-specific `Raises:` sections are on each method, and the errors common to every call are on `AuraClient`.

**Where:** every service method (for example `services/instances.py:245`), plus 10 exported
classes that have no docstring: `CloudProvider`, `CDCEnrichmentMode`, `SnapshotStatus`,
`SnapshotProfile`, `GDSSessionStatus`, `HealthStatus`, `ResourceMetrics`, `QueryMetrics`,
`ConnectionMetrics` and `StorageMetrics`.

**Problem:** `help(client.instances.get)` says "Full details of one instance." but not that
it raises `NotFoundError` or `AuraValidationError`, or what format the ID must be in. The
dataclasses without docstrings show the auto-generated signature in IDE hovers. The client
docstrings do use `Args:` sections, so the style is already set.

**Suggested fix:** add `Raises:` sections at least, because that's what callers need most and
what's hardest to find by reading. Also give each class listed above a one-line docstring.

## Consider

### 11. Rate limits and 5xx responses are never retried
**Status:** Fixed in `5976bb9`, on by default: 429, 502, 503 and 504 are retried for GET, PUT and DELETE, honouring `Retry-After`.

**Where:** `_internal/http/_service.py:24-29`, which is documented in the `max_retries`
docstring.

This is deliberate, for parity with Go, and `RateLimitError.retry_after` lets callers handle
it themselves. Most Python SDKs (stripe, openai, Azure) retry 429 and 503 on idempotent
requests, honouring `Retry-After`, so Python users may expect the same. An opt-in
(`retry_on_status=True`) would keep the Go default. It's safe for GET and DELETE, and it's
already clear that POST isn't retried.

### 12. Timeout and connection errors don't subclass the built-in equivalents
**Status:** Fixed in `b612765`.

**Where:** `_errors.py:30` and `:42`

`AuraConfigurationError` and `AuraValidationError` already inherit from `ValueError`, and
`MetricNotFoundError` from `LookupError`. `AuraTimeoutError` could also inherit from
`TimeoutError`, and `AuraConnectionError` from `ConnectionError`, so that generic handlers such
as `except TimeoutError` in retry libraries catch them. Adding built-in base classes doesn't
break anyone.

### 13. `AuraAPIError` has Go-style `is_not_found` / `is_unauthorized` / `is_bad_request`
**Status:** Kept as Go aliases (`5c15ab2`). The README's Go table lists them.

**Where:** `_errors.py:96-106`

These duplicate the subclasses (404 always maps to `NotFoundError`), so there are two ways to
do the same check, and only three statuses have predicates. They help people coming from Go.
If you keep them, the README's Go section is a good place for them. If not, removing them is
cheapest before 1.0.

### 14. `get_metric_value` is a pure function sitting on the service
**Status:** Fixed in `41c9260`. Added `PrometheusMetrics.value(name, /, **labels)`. `get_metric_value` stays as a Go alias.

**Where:** `services/prometheus.py:166` and `:208`

It does no I/O, which is why it stays synchronous on the async service, an exception the
README has to explain. A method on the data, such as
`metrics.value("neo4j_...", database="neo4j")` on `PrometheusMetrics`, would be the more
natural Python form. The service method could stay as a thin alias for Go parity.

### 15. Timeouts can't be overridden per call
**Status:** Fixed in `d4ff9bb`. Added `with_options(timeout=..., max_retries=...)`.

**Where:** `_client.py:103`. One 120-second deadline covers every call.

Quick reads and slow operations share a single setting. An optional `timeout=` on each method,
or `client.with_options(timeout=5)` (the openai-python pattern), would allow both. This is
useful rather than urgent.

### 16. ID field names differ between models
**Status:** No change, by decision. `snapshot_id` matches the API's field name.

**Where:** `models/instances.py` `Instance.id`, versus `models/snapshots.py`
`Snapshot.snapshot_id` and `CreatedSnapshot.snapshot_id`.

These follow the wire format, which is a sensible default. Callers do end up writing
`instance.id` but `snapshot.snapshot_id`. You could leave it as it is, or add an `id`
property to snapshots. Either is fine; just be consistent from here on.

### 17. A revoked token fails the next call before recovering
**Status:** Fixed in `6cef930`.

**Where:** `_internal/_request.py:87-89`

A 401 invalidates the cached token, but the call still fails, so the call *after* it succeeds.
Retrying once after a 401 with a fresh token would hide token rotation from callers. Keep it
to one retry so bad credentials still fail quickly.

## Done well

- **Client construction:** every option is keyword-only and validated when the client is
  built, HTTPS is enforced, and `repr` hides secrets (`_client.py:96`, `_config.py:29`,
  `CreatedInstance.password`).
- **Exceptions:** there's one `AuraError` base, and the subclasses match the decisions a caller
  has to make. They include `ValueError`/`LookupError` bases, a typed `request_id` and
  `retry_after`, httpx errors wrapped and chained, and tracebacks that report the public module
  path (`_errors.py:251`).
- **Models cope with API changes:** `Enum | str` fields keep unknown values, unknown keys are
  ignored, and null handling is explicit (`_internal/_serde.py:1-12`).
- **Sync and async match:** a script comparing every service pair found identical method names
  and signatures. Shared `Call` objects keep the two from drifting apart (`_internal/_call.py`).
- **Retries never repeat a write:** network-failure retries use `request_sent` tracking, so a
  `POST /instances` is never sent twice (`_internal/http/_service.py:70`).
- **Transports:** they're defined by a public `Protocol` with public request and response
  types. Custom transports and fakes don't have to touch private code, and httpx is confined to
  one module by a test.
- **Typing for callers:** `py.typed` ships and mypy strict passes. Caller code gets precise
  types from mypy, including `Instance` from `await client.instances.get(...)`.
- **Logging:** there's a `NullHandler` and a named logger for each service, and nothing is
  logged at INFO except completed changes.
- **Models:** they're frozen, slotted, keyword-only dataclasses throughout.

## Not checked

- How the live API behaves (for example which fields are really nullable). This review used
  the code and the spec comments in it.
- Performance, and a full security audit beyond what the public surface exposes.
- The tests themselves, which were read only to learn intended behaviour.
