# aura-python-sdk

A Python client for the [Neo4j Aura API](https://neo4j.com/docs/aura/api/overview/) (v1). For
example, `client.instances.list()` returns your Aura instances. It is modelled on
[aura-go-sdk](https://github.com/neo4j-contrib/aura-go-sdk) and covers the whole v1 API.

- Sync (`AuraClient`) and asyncio (`AsyncAuraClient`) clients with the same services.
- Typed throughout (`py.typed`, checked with `mypy --strict`), using frozen dataclass models.
- One runtime dependency, [httpx](https://www.python-httpx.org/), kept behind the SDK's own
  transport interface.
- Client-side validation, automatic OAuth token handling, safe retries, and one exception
  class per error.

You need an Aura API client ID and secret. See
[Aura API authentication](https://neo4j.com/docs/aura/api/authentication/).

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Timeouts and retries](#timeouts-and-retries)
- [Async](#async)
- [Tenants](#tenants)
- [Instances](#instances)
- [Snapshots](#snapshots)
- [Customer-managed keys](#customer-managed-keys)
- [Graph Analytics sessions](#graph-analytics-sessions)
- [Prometheus metrics](#prometheus-metrics)
- [Error handling](#error-handling)
- [Logging](#logging)
- [Custom transports and testing](#custom-transports-and-testing)
- [Coming from the Go SDK](#coming-from-the-go-sdk)
- [Development](#development)

## Installation

Requires Python 3.11 or later.

The SDK is not on PyPI yet. Pre-release builds are published to
[TestPyPI](https://test.pypi.org/project/aura-python-sdk/):

```sh
pip install --pre -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ aura-python-sdk
```

`--pre` is needed because every release so far is a pre-release. `--extra-index-url` lets pip
fetch `httpx` from PyPI, since TestPyPI does not carry it.

## Quick start

```python
import aura_python_sdk as aura

with aura.AuraClient(client_id="your-client-id", client_secret="your-client-secret") as client:
    for instance in client.instances.list():
        print(f"{instance.name} ({instance.id})")
```

Or read the credentials from the `AURA_CLIENT_ID` and `AURA_CLIENT_SECRET` environment
variables:

```python
client = aura.AuraClient.from_env()
client = aura.AuraClient.from_env(timeout=30, max_retries=5)  # any other option, type-checked
```

Using the client as a context manager (or calling `client.close()`) releases its pooled
connections. A closed client raises `AuraClientClosedError` if you use it again.

## Configuration

Every option is keyword-only. An invalid option raises `AuraConfigurationError` straight away.

```python
import logging

client = aura.AuraClient(
    client_id="...",
    client_secret="...",
    timeout=60,  # seconds per call (default 120)
    max_retries=5,  # retries after a network failure or a 429/502/503/504 (default 3)
    max_response_size=20 * 1024 * 1024,  # bytes (default 10 MB)
    base_url="https://api.staging.neo4j.io",
    user_agent="my-app/1.0",  # default "aura-python-sdk/<version>"
    default_headers={"X-Team": "platform"},  # added to every request
    logger=logging.getLogger("my-app.aura"),
)
```

| Option | Default | Notes |
| --- | --- | --- |
| `client_id`, `client_secret` | required | Must not be empty. |
| `base_url` | `https://api.neo4j.io` | Must be HTTPS. |
| `allow_insecure_base_url` | `False` | Allows an `http://` base URL, and metrics URLs outside `*.neo4j.io`. For local test servers only. |
| `timeout` | `120` | Seconds allowed for each call (see below). |
| `max_retries` | `3` | `0` disables retries. |
| `max_response_size` | 10 MB | Larger responses raise `AuraResponseError`. |
| `user_agent` | `aura-python-sdk/<version>` | |
| `default_headers` | none | `Authorization`, `Content-Type` and `User-Agent` are ignored. |
| `logger` | `logging.getLogger("aura_python_sdk")` | |
| `transport` | built-in httpx transport | See [Custom transports](#custom-transports-and-testing). |

## Timeouts and retries

`timeout` is one deadline for the whole call, covering the OAuth token fetch, every retry and
every backoff. This matches the per-call `context.WithTimeout` in the Go SDK.

To change `timeout` or `max_retries` for some calls only, use `with_options()`. It returns a
copy of the client that shares its connections and OAuth token, so it's cheap to call each time:

```python
instance = client.with_options(timeout=5).instances.get("2f49c2b3")

patient = client.with_options(timeout=600, max_retries=10)
patient.instances.list()
```

Closing a copy doesn't close the connections. Closing the original client closes its copies
too.

Retries use backoff from 1 s doubling to 5 s, and stop at `max_retries` or when the next wait
would pass the deadline. Two things are retried:

- **Network failures.** If the request might already have reached the server (a read timeout or
  a dropped connection), only idempotent methods (`GET`, `PUT`, `DELETE`) are retried, so a
  `create` or `pause` is never sent twice. A failure before the request was sent (DNS, connect)
  is retried for every method.
- **429, 502, 503 and 504 responses, for idempotent methods only.** The client waits for the
  server's `Retry-After` when it sends one. If that wait would pass the deadline, it raises
  straight away, and `RateLimitError.retry_after` tells you how long the server asked for.

Any other response, including a 500, raises its error without a retry. The Go SDK never retries
a response; this follows other Python SDKs, such as stripe and openai, instead.

If the API rejects the cached OAuth token with a 401 (for example because it was revoked), the
client fetches a new token and sends the request once more. The API rejected the first attempt
without acting on it, so this is safe for every method. A second 401 raises
`AuthenticationError`.

## Async

`AsyncAuraClient` takes the same options, and its services have the same methods, which you
await. Concurrent calls share one OAuth token.

```python
import asyncio

import aura_python_sdk as aura


async def main() -> None:
    async with aura.AsyncAuraClient.from_env() as client:
        summaries = await client.instances.list()
        instances = await asyncio.gather(*(client.instances.get(s.id) for s in summaries))
        for instance in instances:
            print(instance.name, instance.status)


asyncio.run(main())
```

Use `async with` or `await client.aclose()` to release connections. `prometheus.get_metric_value`
does no I/O, so it is a plain method on both clients. A custom transport for the async client
implements `AsyncHttpTransport` (`async send()` and `async aclose()`).

## Tenants

```python
for tenant in client.tenants.list():
    print(tenant.id, tenant.name)

tenant = client.tenants.get("6981ace7-efe8-4f5c-b7c5-267b5162ce91")
for config in tenant.instance_configurations:
    print(config.type, config.cloud_provider, config.region, config.memory, config.version)

endpoint = client.tenants.get_metrics_integration(tenant.id).endpoint
```

## Instances

```python
from aura_python_sdk import CloudProvider, InstanceConfig, InstanceStatus, InstanceType

instances = client.instances.list()  # or list(tenant_id=...)
instance = client.instances.get("2f49c2b3")
if instance.status == InstanceStatus.RUNNING:
    print(instance.connection_url)

created = client.instances.create(
    InstanceConfig(
        name="my-instance",
        tenant_id="6981ace7-efe8-4f5c-b7c5-267b5162ce91",
        cloud_provider=CloudProvider.GCP,
        region="europe-west1",
        type=InstanceType.PROFESSIONAL_DB,
        version="5",
        memory="2GB",
    )
)
print(created.id, created.username, created.password)  # the password is shown only once
```

Creation is asynchronous. `wait_for_status()` polls `get()` until the instance reaches a status
(`running` by default), and raises `OperationFailedError` if loading fails or `WaitTimeoutError`
after `timeout` (15 minutes by default). See
[examples/create_delete_instance.py](examples/create_delete_instance.py).

```python
created = client.instances.create(config)
instance = client.instances.wait_for_status(created.id)
client.instances.pause(instance.id)
client.instances.wait_for_status(instance.id, status=aura.InstanceStatus.PAUSED)
```

Use it after `create`, `pause` and `resume`, which each end in a status the instance wasn't
already in. `update`, `upgrade`, overwrites and restores start and end in `running`, so the first
poll may still see the old status and return at once; `wait_for_status()` can't tell you when
those have finished.

| Method | What it does |
| --- | --- |
| `list(*, tenant_id=None)` | Summaries of every instance, optionally in one tenant. |
| `get(instance_id)` | Full details. |
| `create(config)` | Starts creating an instance. Returns the initial credentials. |
| `create_from_instance(config, *, source_instance_id)` | Clones another instance's current data. |
| `create_from_snapshot(config, *, source_instance_id, source_snapshot_id)` | Creates from an exportable snapshot. |
| `update(instance_id, *, name, memory, storage, vector_optimized, graph_analytics_plugin, cdc_enrichment_mode, secondaries_count)` | Changes only the fields you pass. |
| `pause(instance_id)` / `resume(instance_id)` | |
| `delete(instance_id)` | Cannot be undone. |
| `overwrite_from_instance(instance_id, *, source_instance_id)` | Replaces the data with another instance's. |
| `overwrite_from_snapshot(instance_id, *, source_snapshot_id)` | Replaces the data with a snapshot. |
| `estimate_size(*, node_count, relationship_count, instance_type, algorithm_categories)` | Sizing for AuraDS instances. |
| `upgrade(instance_id, *, memory, storage)` | Professional to Business Critical. Pass both sizes, or neither. |
| `wait_for_status(instance_id, *, status=RUNNING, timeout=900, interval=10)` | Polls until the instance has `status`. |

`CreatedInstance.password` is left out of `repr()`, so logging the object doesn't expose it.

## Snapshots

```python
import datetime

snapshots = client.snapshots.list("2f49c2b3")  # today
snapshots = client.snapshots.list("2f49c2b3", date=datetime.date(2026, 9, 1))

started = client.snapshots.create("2f49c2b3")
snapshot = client.snapshots.wait_for_completion("2f49c2b3", started.snapshot_id)
client.snapshots.restore("2f49c2b3", snapshot.snapshot_id)
```

`wait_for_completion()` polls until the snapshot is `Completed`, and raises
`OperationFailedError` if it fails or is cancelled.

## Customer-managed keys

```python
keys = client.cmek.list()  # or list(tenant_id=...)
key = client.cmek.create(
    name="Production Key",
    key_id="arn:aws:kms:us-west-2:111122223333:key/1234abcd-...",
    tenant_id="6981ace7-efe8-4f5c-b7c5-267b5162ce91",
    cloud_provider=CloudProvider.AWS,
    region="us-west-2",
    instance_type=InstanceType.ENTERPRISE_DB,
)
print(client.cmek.get(key.id).status)
client.cmek.delete(key.id)
```

## Graph Analytics sessions

```python
from aura_python_sdk import GDSSessionConfig

estimate = client.graph_analytics.estimate_size(node_count=1_000_000, relationship_count=5_000_000)

session = client.graph_analytics.create(
    GDSSessionConfig(
        name="analysis",
        memory=estimate.recommended_size,
        ttl="1h",
        tenant_id="6981ace7-efe8-4f5c-b7c5-267b5162ce91",
        cloud_provider=CloudProvider.GCP,
        region="europe-west1",
    )
)
session = client.graph_analytics.wait_until_ready(session.id)
sessions = client.graph_analytics.list(tenant_id=session.tenant_id)
client.graph_analytics.delete(session.id)
```

## Prometheus metrics

Get a metrics endpoint from `tenants.get_metrics_integration()` or from an instance's
`metrics_integration_url`. The client sends its Aura token to that endpoint, so only
`https://*.neo4j.io` URLs are accepted.

```python
instance = client.instances.get("2f49c2b3")
url = instance.metrics_integration_url

metrics = client.prometheus.fetch_raw_metrics(url)
cpu = client.prometheus.get_metric_value(
    metrics, "neo4j_aura_cpu_usage", {"instance_mode": "PRIMARY"}
)

health = client.prometheus.get_instance_health(instance.id, url)
print(health.overall_status, health.issues, health.recommendations)
```

`get_metric_value` averages every matching sample, and raises `MetricNotFoundError` if nothing
matches. `get_instance_health` uses the Go SDK's metrics and thresholds. A metric the endpoint
doesn't report comes back as `None`, not `0`.

## Error handling

Every exception derives from `AuraError`:

```text
AuraError
├── AuraConfigurationError   (ValueError)  bad client options
├── AuraValidationError      (ValueError)  bad arguments; nothing was sent
├── AuraConnectionError   (ConnectionError) network failure after retries
│   └── AuraTimeoutError  (TimeoutError)
├── AuraClientClosedError (RuntimeError)   the client was used after close()
├── AuraResponseError                      oversized or malformed response
├── OperationFailedError                   a wait_* helper saw the operation fail
├── WaitTimeoutError     (TimeoutError)    a wait_* helper gave up; .resource is the last state
├── MetricNotFoundError      (LookupError)
└── AuraAPIError                           non-2xx response
    ├── BadRequestError         400
    ├── AuthenticationError     401, or rejected credentials
    ├── PermissionDeniedError   403
    ├── NotFoundError           404
    ├── ConflictError           409
    ├── RateLimitError          429  (.retry_after in seconds)
    └── ServerError             5xx
```

```python
try:
    client.instances.get("2f49c2b3")
except aura.NotFoundError:
    print("no such instance")
except aura.AuraAPIError as err:
    print(err.status_code, err.message, err.request_id)
    for detail in err.details:
        print(detail.reason, detail.field, detail.message)
```

The standard-library base classes in brackets mean generic handlers work too: for example,
`except TimeoutError` in a retry library catches `AuraTimeoutError`. Every SDK exception can be
pickled, so it survives `multiprocessing` and `concurrent.futures.ProcessPoolExecutor`.

`AuraAPIError` also provides the Go SDK's helpers: `is_not_found`, `is_unauthorized`,
`is_bad_request`, `has_multiple_errors` and `all_errors()`.

## Logging

The SDK logs through the standard `logging` module under the `aura_python_sdk` logger, and
emits nothing unless your application configures logging. Requests are logged at `DEBUG`, and
started mutations (create, delete, pause and so on) at `INFO`. Credentials, tokens and passwords
are never logged.

```python
logging.basicConfig()
logging.getLogger("aura_python_sdk").setLevel(logging.DEBUG)
```

## Custom transports and testing

Pass any object with `send(request) -> HttpResponse` and `close()` as `transport=`. For
`AsyncAuraClient`, pass one with `async send()` and `async aclose()`. Each client rejects the
other kind. This is the
equivalent of the Go SDK's `WithHTTPClient`. The SDK's retries, auth and error mapping still
apply on top. A client never closes a transport it didn't create.

```python
from aura_python_sdk import AuraClient, HttpRequest, HttpResponse


class RecordingTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.responses.pop(0)

    def close(self) -> None:
        pass
```

For a network failure, a transport should raise `AuraConnectionError` or `AuraTimeoutError`. Set
`request_sent=False` only when the server certainly never received the request, because that
decides whether a `POST` is retried.

`repr(request)` is safe to log: it replaces the `Authorization` value with `***` and shows only
the body's length. `request.headers` still holds the real values, which the transport needs to
send.

## Coming from the Go SDK

| Go | Python |
| --- | --- |
| `aura.NewClient(aura.WithCredentials(id, secret), aura.WithTimeout(t))` | `aura.AuraClient(client_id=id, client_secret=secret, timeout=t)` |
| `defer client.Close()` | `with aura.AuraClient(...) as client:` |
| goroutines with a shared client | `AsyncAuraClient` with `asyncio.gather` |
| `client.Instances.List(ctx)` returning `resp.Data` | `client.instances.list()` returns the list |
| `aura.IsNotFound(err)` | `except aura.NotFoundError:` |
| `aura.WithHTTPClient(c)` | `transport=` |
| `aura.WithInsecureBaseURL(u)` | `base_url=u, allow_insecure_base_url=True` |
| `client.Tenants.GetMetrics` | `client.tenants.get_metrics_integration` |
| `client.GraphAnalytics.Estimate` | `client.graph_analytics.estimate_size` |
| `SnapshotDate` / `aura.Today()` | `datetime.date` / omit it for today |
| `PrometheusHealthMetrics.Query.AvgLatencyMs` (the q50 median) | `InstanceHealth.query.median_latency_ms` |

Python additions: sizing and upgrade for instances; get, create and delete for customer-managed
keys; list filters; and the full set of `update` fields. The design notes are in
[PLAN.md](PLAN.md).

## Examples

[examples/](examples/) contains ports of the Go SDK's v1 examples. Each one reads
`AURA_CLIENT_ID` and `AURA_CLIENT_SECRET` from the environment:

```sh
uv run python examples/list_instances.py
```

## Development

```sh
uv sync --all-extras
uv run ruff format && uv run ruff check
uv run mypy
uv run pytest                     # unit and local black-box tests; no network
```

The live tests in `tests/integration/` call the real Aura API, and are skipped unless credentials
are set. They are read-only unless you opt in to creating and deleting an instance:

```sh
AURA_CLIENT_ID=... AURA_CLIENT_SECRET=... uv run pytest -m integration
AURA_INTEGRATION_WRITE=1 AURA_TENANT_ID=... uv run pytest -m integration   # also creates/deletes
```

The package version comes from the latest git tag, via
[hatch-vcs](https://github.com/ofek/hatch-vcs), which writes `src/aura_python_sdk/_version.py`
when the package is built or installed. That file is not in git, so run `uv sync` in a fresh
clone before importing the package. Between tags, `__version__` has a local suffix such as
`0.1.1.dev3+g8d7381f` (three commits after `v0.1.0`, at commit `8d7381f`).

### Releasing

Releases are published to TestPyPI only for now. There is no version number to edit:

1. Merge the changes to `main`.
2. On `main`, add a `## vX.Y.Z` section to [CHANGELOG.md](CHANGELOG.md), and commit and push
   it. That section becomes the GitHub release notes.
3. Tag the commit and push the tag:

   ```sh
   git tag v0.1.0.dev1
   git push origin v0.1.0.dev1
   ```

The tag must be `v` followed by a
[normalised Python version](https://packaging.python.org/en/latest/specifications/version-specifiers/),
for example `v0.1.0`, `v0.2.0rc1` or `v0.1.0.dev2`, not `v0.1.0-dev1`. The workflow fails
if the built version does not match the tag. Tags containing `dev`, `a`, `b` or `rc` become
GitHub pre-releases.

Pushing the tag runs [the release workflow](.github/workflows/release.yml). It runs the lint,
type and test checks, builds the package, publishes to TestPyPI and creates the GitHub release.
TestPyPI never accepts the same version twice, so a fix needs a new tag. Re-running the
workflow for an existing tag leaves the uploaded files unchanged.

## License

MIT. See [LICENSE](LICENSE).
