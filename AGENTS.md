# AGENTS.md

Guidance for LLM agents working on `aura-python-sdk`, a Python client for the Neo4j Aura API v1.
It is modelled on the v1 surface of [aura-go-sdk](https://github.com/neo4j-contrib/aura-go-sdk).
For users, see [README.md](README.md). [PLAN.md](PLAN.md) records the design and the decisions
behind it, so read the relevant section before changing behaviour. The API definition is
`aura_api_spec_v1 .yaml` (the filename contains a space; quote it).

## Commands

```sh
uv sync --all-extras                  # fresh clone: also generates src/aura_python_sdk/_version.py
uv run ruff format && uv run ruff check
uv run mypy                           # strict; covers src, tests and examples
uv run pytest                         # no network; integration tests are deselected by default
```

CI runs `ruff format --check`, `ruff check`, `mypy` and `pytest` on Python 3.11 to 3.14. All four
must pass before you finish. Keep code compatible with 3.11 (`requires-python = ">=3.11"`).

Never run `pytest -m integration` unless the user asks. It calls the real Aura API, and
`AURA_INTEGRATION_WRITE=1` creates a billed instance. `.env` holds real credentials; don't read,
print or commit it.

## Architecture

```
AuraClient / AsyncAuraClient       _client.py   config + grouped services (client.instances.list())
  ▼
services/*.py                      one sync and one async class per API area
  ▼  build a Call (no I/O)
_internal/_call.py                 Call: method, path, params, body, parse function
  ▼
_internal/_request.py              RequestService: OAuth token cache, URL building, headers,
  ▼                                status → exception mapping
_transport.py                      HttpTransport / AsyncHttpTransport Protocols (ours)
  ▼
_internal/http/_httpx.py           the only module that imports httpx or truststore
```

- **Sync and async share one definition.** A service method validates its arguments and returns
  a `Call`; `Service` (sync) and `AsyncService` run it through their own request service. Put
  validation, paths, bodies and parsing in the shared part. `InstanceService` and
  `AsyncInstanceService` live in the same file and must expose the same methods and signatures.
- **Models** are in `models/`, one file per API area, parsed by `_internal/_serde.py`. Service
  methods unwrap the API's `data` envelope and return models or lists of models directly.
- **Errors** are in `_errors.py`, all subclasses of `AuraError`. Raise SDK errors, never httpx
  ones. Config problems raise `AuraConfigurationError` (a `ValueError`), bad arguments
  `AuraValidationError`. Only `AuraError` subclasses have their tracebacks trimmed, so unexpected
  exceptions keep theirs.
- **Public API** is `aura_python_sdk/__init__.py` (`__all__`) plus the service classes. Anything
  with a leading underscore, and everything under `_internal/`, is private.

## Rules that tests enforce

- **Third-party imports are wrapped.** Each dependency is imported by exactly one module
  (`tests/unit/test_import_boundaries.py` lists them). Don't import `httpx` or `truststore`
  outside `_internal/http/_httpx.py`, and don't let a dependency type appear in a public
  signature. A new dependency needs an entry in that test's `WRAPPED_DEPENDENCIES`.
- **Public surface is frozen.** `tests/unit/api_surface.txt` is a snapshot of every exported
  class, field, enum member and method signature. If you change the surface on purpose, run
  `AURA_UPDATE_SURFACE=1 uv run pytest tests/unit/test_api_surface.py`, review the diff, and
  commit the updated file. Never regenerate it to silence an unexpected failure.
- **Sync/async parity.** `tests/unit/test_async_parity.py` runs every service method through both
  clients and compares requests, results and signatures. A new method needs a case there.
- **Live write test guard.** `tests/unit/test_live_test_guards.py` checks the integration write
  test keeps its skip condition on the test itself. Don't move it.

## Conventions

- Match the surrounding code: comment density, naming, idiom. Comments say why, not what.
- Python names are snake_case versions of the Go SDK's, with unwrapped returns and keyword-only
  options. `PLAN.md` §2 has the translation table; keep new methods consistent with it.
- Validate every ID and user-supplied path segment with `_validation.py` before it reaches a URL.
  IDs of `.` or `..` are rejected on purpose.
- Security-sensitive behaviour is deliberate and documented in
  [docs/security-review.md](docs/security-review.md): HTTPS-only base URLs, the Prometheus URL
  allowlist (`allow_untrusted_metrics_urls`), refusing HTTPS to HTTP redirects, secrets kept out
  of `repr`, TLS verified against the OS trust store. Read the relevant entry before loosening
  any of them.
- The Aura token must only go to the API and to allowed metrics hosts. Be careful with anything
  that adds a request path, follows a redirect or builds a URL.

## Tests

- `tests/unit/`: no network, uses the fakes in `tests/fakes.py` (`FakeTransport`,
  `FakeAsyncTransport`). Add a test with every change.
- `tests/blackbox/`: drives the public client end to end against a local server.
- `tests/transport/`: `HttpxTransport` against `httpx.MockTransport`. Tests may import httpx.
- `tests/integration/`: live API; see above.

## Docs, changelog and releases

- Add user-visible changes to the `## Unreleased` section of [CHANGELOG.md](CHANGELOG.md), under
  Added, Changed or Fixed, and mark breaking changes **Breaking**. Update the README if usage
  changes, and the examples in `examples/` (they are type-checked).
- The version comes from git tags via hatch-vcs; never edit a version number.
- Releasing follows the "Releasing" section of the README: rename `Unreleased` in the PR, merge,
  then tag the merge commit `vX.Y.Z` and push the tag. Pushing the tag publishes to PyPI, so
  only do it when the user asks.
- Open a pull request rather than pushing to `main`, and don't merge one without being asked.
