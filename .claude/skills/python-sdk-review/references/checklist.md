# Python SDK surface checklist

Work through these sections in order. Each item says what to look for and why it matters to a
caller. Where the answer depends on context, the item says what the trade-off is.

## Contents

1. Package, exports and privacy
2. Naming
3. Client construction and configuration
4. Method signatures
5. Return types and models
6. Typing for callers
7. Errors
8. Sync and async
9. Pagination and collections
10. Timeouts, retries and long-running operations
11. Resource lifecycle
12. Transport, extensibility and testing
13. Logging and observability
14. Docstrings and discoverability
15. Versioning, compatibility and packaging

---

## 1. Package, exports and privacy

- **`__all__` is present and complete.** Every name a caller needs is in it, and nothing
  internal is. Star-imports, IDEs and `help()` use it, and it acts as the package's public API
  contract.
- **The top-level import is enough for normal use.** A caller can build a client, catch
  every error and annotate every return value using `from pkg import ...` or one documented
  subpackage (for example `pkg.models`). If they need `pkg._something`, that name is
  effectively public without the stability promise.
- **The privacy convention is consistent.** Modules or packages with a leading underscore are
  private. Public modules don't re-export private helpers by accident: check for names that
  are imported into a public module and so become reachable from it.
- **`py.typed` ships in the wheel,** and the package is listed as `Typing :: Typed`.
- **Importing the package is cheap and has no side effects:** no network calls, no reading
  config files, no configuring logging, no heavy optional imports at import time.
- **Optional dependencies are optional.** Anything outside core use is in an extra, and a
  missing extra raises a clear error that says which extra to install.

## 2. Naming

- **PEP 8:** `snake_case` functions, methods and attributes; `CapWords` classes;
  `UPPER_CASE` constants. Names carried over from another language's SDK or from the wire
  format (`camelCase`, `Id` suffixes, Go-style `GetX`) are a finding.
- **Methods are consistent across services.** Verbs are the same everywhere (`list`/`get`/
  `create`/`update`/`delete`), not `get_all` in one service and `list` in another. Identifier
  parameters are named the same way everywhere (`instance_id`, not `id` in one place and
  `instance` in another).
- **Booleans read as booleans** (`is_`, `has_`, or an adjective), and don't shadow builtins
  (`id`, `type`, `filter`, `list`, `hash`) in *parameters*. Attributes named after builtins
  are less of a problem but still worth noting.
- **Enums or `Literal` types are used for closed sets of values,** named in the singular
  (`InstanceStatus.RUNNING`). Enum values match the wire format, and the SDK copes with values
  it doesn't know yet (see section 5).
- **No stutter:** `pkg.instances.InstancesInstance` or `client.instances.list_instances()`
  repeat the context the caller already has.

## 3. Client construction and configuration

- **Construction arguments are keyword-only** (`def __init__(self, *, client_id, ...)`), so
  options can be added or reordered later without breaking callers.
- **Credentials:** there's an explicit argument, an environment-variable route
  (`from_env()` or a default), and it's clear which one wins. Secrets never appear in `repr()`,
  exception messages or logs. Check the config object's `__repr__` and any dataclass fields.
- **Defaults are safe and documented:** there's a timeout (never an infinite default), bounded
  retries, and TLS verification on.
- **Invalid configuration fails at construction time** with a clear message, not on the first
  request.
- **Configuration is immutable once the client is built,** or changes to it are clearly
  defined. Sharing one client between threads or tasks is either safe or documented as unsafe.

## 4. Method signatures

- **Required identifiers can be positional; everything else is keyword-only.**
  `get(instance_id)` is fine. `create(name, version, region, memory, ...)` taking seven
  positional parameters isn't, because adding or reordering parameters breaks callers silently.
- **Two positional arguments of the same type with different meanings** (target and source ID,
  `copy(src, dst)`) are a must-fix when swapping them does damage (overwrite, delete, move).
  The type checker can't catch a swap between two `str` arguments, so only naming the argument
  protects the caller.
- **Mutable defaults** (`=[]`, `={}`) are never used.
- **"Not set" and "explicitly null" are distinct** where the API treats them differently
  (PATCH-style updates). A sentinel or `None` is used for this, and the choice is documented.
- **Parameter types accept what callers naturally have:** `Sequence`/`Iterable` rather than
  `list`, `Mapping` rather than `dict`, `str | Enum` where an enum is offered, `datetime` rather
  than an ISO string, `timedelta` or seconds as a float for durations (and the unit is
  documented).
- **Complex request bodies:** a caller either passes keyword arguments or a typed request
  object. Pick one pattern and use it everywhere. Taking a raw `dict` loses type checking.
- **Per-call overrides** (timeout, extra headers, idempotency key) are available where
  callers would need them, and use the same names everywhere.
- **`**kwargs` passed through to another function** (`from_env(**options)`) switch off
  type checking for every option, so a mistyped option name only fails when the code runs. Use
  `**kwargs: Unpack[SomeTypedDict]` (PEP 692) or repeat the parameters explicitly. A
  `# type: ignore` on the pass-through call is the tell-tale sign.

## 5. Return types and models

- **Return values are typed models, not raw `dict`s,** unless a dict is explicitly the
  contract.
- **Frozen dataclasses, attrs or pydantic** are used consistently. Frozen models are hashable
  and safe to share, but callers then need `dataclasses.replace` to change them: check whether
  that's documented anywhere it matters.
- **Models tolerate API changes:** unknown fields are ignored rather than raising, unknown enum
  values don't crash parsing (they fall back to a raw string or an `UNKNOWN` member), and new
  optional fields don't break callers. This is the most common way SDKs break in production
  without any SDK change.
- **Optional fields are typed `X | None`,** matching what the API actually returns, not what
  it's documented to return. Check for fields typed as non-optional that the API can return as
  null.
- **Field types are Pythonic:** `datetime` (timezone-aware) rather than strings, `int`/`float`
  for numbers, enums for closed sets.
- **`repr()` is useful and safe:** it shows identifying fields and hides secrets (for example
  connection passwords returned by a create call).
- **Raw response access:** if callers ever need headers, status or the raw body, there's a
  documented way to get them.

## 6. Typing for callers

Review typing from the caller's side, not the implementation's side.

- **Write a small caller script and run `mypy --strict` on it.** Does it infer the right types
  from `client.x.get(...)`, including awaitables for the async client? Are there `Any`s leaking
  out that callers can't narrow?
- **Overloads** are used where the return type depends on an argument (for example
  `wait=True` returns the finished resource, `wait=False` returns an operation object).
- **Protocols** are used for things callers implement (transports, auth hooks), so callers
  don't have to subclass something internal.
- **Public generics** are parameterised correctly and exported, if callers are expected to
  annotate with them (for example `Page[Instance]`).

## 7. Errors

- **There's one base exception** (`PkgError`) that every SDK-raised error inherits from, so
  `except PkgError` catches everything the SDK raises on purpose.
- **Subclasses match how callers decide what to do**, not every HTTP status code: auth,
  permission, not found, conflict, validation, rate limited, server error, timeout or
  connection. Check that callers can tell "retry this" apart from "fix your input".
- **Errors carry the context a caller needs:** status code, the API's error code or message,
  a request ID for support, and the retry-after for rate limits, as typed attributes rather
  than only in the message string.
- **Transport exceptions are wrapped** (`httpx.TimeoutException` becomes `PkgTimeoutError`),
  with the original chained using `raise ... from e`. Otherwise callers have to catch a
  dependency's exception types, which makes that dependency part of your API.
- **Validation errors** on bad arguments raise `ValueError`/`TypeError` or a subclass of them,
  so generic Python error handling still works.
- **Exception messages don't leak secrets** (tokens, client secrets, connection passwords).
- **Exceptions survive pickling.** Custom `__init__` signatures (required keyword-only
  arguments, or more than one positional argument) break `pickle`, which in turn breaks
  `ProcessPoolExecutor`, `multiprocessing`, Celery and Dask. The caller then gets a confusing
  `TypeError` in place of the real error. Check with
  `pickle.loads(pickle.dumps(exc))` for each exported exception.

## 8. Sync and async

- **The two clients have the same shape:** same services, same method names, same
  parameters, and results that differ only by `await`. Check with a quick script that
  compares method names and signatures, rather than by eye.
- **Naming:** the async client is `AsyncX`, and its close method is `aclose()` or `close()`
  used consistently. `async with` is supported.
- **The async client doesn't block the event loop:** no `time.sleep`, no sync HTTP calls, no
  sync file I/O on request paths. Token refresh is also async, and protected against several
  tasks refreshing at once.
- **Shared logic isn't duplicated** in a way that lets the two clients drift apart. This is
  worth a comment either way.

## 9. Pagination and collections

- **What does `list()` return?** A complete list (simple, but unbounded memory and latency)
  or an iterator or pager (scales, but is less obvious to use). Either can be right. Check
  that the choice suits how big the collections can get, and that it's documented.
- **If the API paginates, the SDK doesn't silently return only the first page.**
- **Filters** use keyword arguments with the same names and types across services.

## 10. Timeouts, retries and long-running operations

- **Retries apply only to safe cases:** idempotent methods, or requests with an idempotency
  key, plus connection errors, 429 and 5xx responses. They use backoff with jitter and honour
  `Retry-After`. Retrying a non-idempotent `POST` without a key is a must-fix.
- **Retry and timeout settings** can be changed on the client and overridden per call, and
  the defaults are documented.
- **Long-running operations** (create, delete, restore) have a clear pattern: either return
  immediately with a way to poll or wait, or offer a `wait_for_*` helper with a timeout and a
  polling interval. The waiting helper raises a timeout error and never blocks forever.

## 11. Resource lifecycle

- **Clients are context managers** (`with`/`async with`) and have an explicit `close()`.
- **Using a closed client** gives a clear error, not a confusing transport error.
  Actually try it: a call after `close()` often raises the HTTP library's own `RuntimeError`,
  which gets past `except PkgError` and exposes the dependency.
- **Clients don't depend on `__del__`** for cleanup. If they warn about unclosed resources,
  it's through `ResourceWarning`.
- **Clients passed in by the caller aren't closed by the SDK.** If a caller supplies their own
  `httpx.Client`, the SDK shouldn't close it unless that's documented.

## 12. Transport, extensibility and testing

- **Callers can inject a transport or HTTP client** (for proxies, custom TLS, instrumentation
  or tests) without monkeypatching.
- **The extension points are public, documented and typed** (a `Protocol` is ideal), and
  callers don't have to import from private modules to implement them.
- **The request and response types handed to extension points don't print secrets.** A
  public `HttpRequest` dataclass whose default `repr` includes headers will write bearer tokens
  to logs as soon as someone logs the request inside their transport.
- **There's a testing story for callers:** a fake transport, recorded responses or an
  in-memory mode that callers can use in their own tests.
- **The `User-Agent` header** identifies the SDK and version, and callers can add to it.

## 13. Logging and observability

- **The SDK uses a named logger** (`logging.getLogger("pkg")`), adds only a `NullHandler`, and
  never calls `basicConfig`.
- **Logging levels are sensible:** request and response summaries at DEBUG, retries at
  INFO/WARNING, and nothing noisy at INFO by default.
- **Secrets are never logged,** including in headers, bodies and URLs at DEBUG level.
- **Request IDs** from the API are logged and exposed, so callers can correlate them with
  support.

## 14. Docstrings and discoverability

- **Every public class, method and function has a docstring** (PEP 257), with a one-line
  summary, the parameters and their units, what's returned, and which exceptions are raised.
  One docstring style is used throughout (Google, NumPy or reST).
- **`help(client.instances.create)`** tells a caller enough to call it correctly without
  opening the source.
- **The README's examples run against the current code.** Check a few against the actual
  signatures, because out-of-date docs are a common finding.
- **Docstrings don't contradict the types** (for example saying "returns a list" when the
  method returns an iterator).

## 15. Versioning, compatibility and packaging

- **`__version__` is exposed** and matches the installed distribution metadata.
- **The stability promise is stated:** SemVer, and what counts as public. Pre-1.0 releases
  should say what may change.
- **There's a deprecation route:** `warnings.warn(..., DeprecationWarning, stacklevel=2)` for
  anything being removed, and it's recorded in the CHANGELOG.
- **`requires-python`** matches the syntax actually used and what CI tests.
- **Dependency bounds** aren't so tight that they conflict with other packages
  (`httpx==0.27.0` is bad), and not unbounded for dependencies known to make breaking changes.
- **Metadata:** licence, project URLs, classifiers and a README that renders on PyPI.
