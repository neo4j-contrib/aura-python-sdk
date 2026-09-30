# aura-python-sdk security review

**Scope:** `main` at v0.1.2 (`69c7f5c` plus the release commit). Each finding now has a
**Status** line. This covers the SDK source, the
default httpx transport, the README install instructions, the CI and release workflows, and
the GitHub repository settings that control publishing. It doesn't cover the Aura API itself.

**Summary:** The SDK's own handling of credentials is solid. The bearer token only goes to the
API or to `https://*.neo4j.io`, and the allowlist held up against 25 URL parser-confusion
tricks. httpx drops the token on any cross-origin redirect. Nothing sensitive reached the logs
across the success, error and retry paths. The most important finding isn't in the code. The
README's install command, combined with the `aura-python-sdk` name being unclaimed on PyPI, lets
anyone who registers the name there get their code installed instead (#1). The remaining
findings are low severity or hardening.

Every finding below was confirmed by running code or querying GitHub or PyPI, unless it says
otherwise.

| # | Severity | Finding |
| --- | --- | --- |
| 1 | Medium | The README install command allows dependency confusion, and the name is unclaimed on PyPI |
| 2 | Low (Medium before PyPI) | Anyone with write access can publish, and the release actions are pinned by mutable tags |
| 3 | Low | `.` and `..` as a CMEK key ID or GDS session ID send the request to a parent path |
| 4 | Low | The access token appears in `_Token`'s `repr`, and `default_headers` in `ClientConfig`'s |
| 5 | Low | Redirects from HTTPS to HTTP are followed |
| 6 | Low | Deeply nested JSON raises `RecursionError`, not an SDK error |
| 7 | Info | `allow_insecure_base_url` also turns off the Prometheus allowlist |

---

## 1. The README install command allows dependency confusion (Medium)

**Status:** Fixed. The name is claimed on PyPI (v0.1.2 was uploaded on 2026-09-30), and since v0.1.3 the README says `pip install aura-python-sdk` with no `--extra-index-url` (PR #6). Releases publish to PyPI through trusted publishing.

**Where:** `README.md`, the Installation section:
`pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ aura-python-sdk`

**Problem:** with `--extra-index-url`, pip treats TestPyPI and PyPI as one pool and installs the
highest version it finds on either. `aura-python-sdk` isn't registered on PyPI (both
`aura-python-sdk` and `aura_python_sdk` return 404). Anyone can register it and upload, say,
version `99.0`, and everyone who follows the README then installs that package instead of the
SDK. That code runs on the user's machine, where their Aura credentials usually are too. Pinning `==0.1.2` doesn't
fully protect callers either, because an attacker can publish the same version number.

TestPyPI is also a lower-trust index in its own right: anyone can register a name there, and it's
periodically wiped. That's acceptable for trying a pre-release, but not as the long-term install
route.

**Suggested fix:**

1. **Now:** change the README to a command that can't mix the two indexes:
   ```sh
   pip install "httpx>=0.27,<1"
   pip install --no-deps -i https://test.pypi.org/simple/ aura-python-sdk
   ```
2. **Soon:** claim the name on PyPI by publishing a real release. This is already planned: add
   the PyPI trusted publisher and restore the `publish` job. That also removes the need for
   TestPyPI instructions. A PyPI "pending publisher" does **not** reserve the name until the
   first upload.

## 2. Anyone with write access can publish, and the release actions are pinned by mutable tags (Low now, Medium before PyPI)

**Status:** Partly done. The `pypi` environment exists and only allows `v*` tags, but has no required reviewer. There are no rulesets for tags or `main`, and the actions are still pinned by tag.

**Where:** the GitHub repository settings, and `.github/workflows/release.yml`

**Problem:**

- The `testpypi` environment only allows `v*` tags, but has no required reviewers. There are no
  rulesets protecting tags or `main`. Any of the 4 people with write access can push to `main`
  and push a tag, and that publishes with no second person involved.

- The jobs that hold publishing credentials run third-party actions pinned by tag or branch:
  `pypa/gh-action-pypi-publish@release/v1` and `actions/download-artifact@v8` alongside
  `id-token: write`, and `softprops/action-gh-release@v3` alongside `contents: write`. Anyone who
  compromises one of those actions can move the tag. The repository has `sha_pinning_required:
  false`. `setup-uv` is pinned to an exact version, `v10.2.0`, but that's still a tag rather than
  a commit SHA.

The impact is limited while releases go only to TestPyPI, and it becomes real with PyPI.

**Suggested fix, before the first PyPI release:**

- Add a required reviewer to the `pypi` environment when it's created, and consider one for
  `testpypi`.

- Add a tag ruleset so only maintainers can create `v*` tags, and a branch ruleset for `main`
  that requires a PR and passing CI.

- Pin the actions in `release.yml` to full commit SHAs, with the version in a comment, and add
  Dependabot for `github-actions` to keep them current.

## 3. `.` and `..` as a CMEK key ID or GDS session ID send the request to a parent path (Low)

**Status:** Open.

**Where:** `src/aura_python_sdk/_internal/_request.py:19` (`build_path`), plus
`services/cmek.py` and `services/graph_analytics.py`, which only check these IDs are non-empty.
Instance, tenant and snapshot IDs are format-validated, so they aren't affected.

**Problem:** `build_path` percent-encodes each segment, so `/`, `?` and `#` in an ID are harmless.
I confirmed this with the raw path on the wire: `../../instances/x` goes out as
`..%2F..%2Finstances%2Fx`. The exact segments `.` and `..` survive encoding, though, and httpx
resolves them:

| Call | Request sent |
| --- | --- |
| `client.cmek.delete("..")` | `DELETE /v1` |
| `client.cmek.delete(".")` | `DELETE /v1/customer-managed-keys` |
| `client.graph_analytics.delete("..")` | `DELETE /v1/graph-analytics` |

An ID can only reach a parent path, not another resource, and the API should reject these
requests. It only matters if an application passes untrusted input through as an ID, but a
`delete` method sending `DELETE` somewhere else is worth closing off.

**Suggested fix:** raise `AuraValidationError` in `build_path` for a segment that is `.` or `..`.
That protects every service at once.

## 4. The access token appears in `_Token`'s `repr`, and `default_headers` in `ClientConfig`'s (Low)

**Status:** Open.

**Where:** `src/aura_python_sdk/_internal/_auth.py:29` (`_Token`) and
`src/aura_python_sdk/_config.py:26` (`ClientConfig`)

**Problem:** `repr(_Token(...))` includes `access_token='…'`. Crash reporters that record frame
locals, such as Sentry by default, call `repr` on locals in the auth code's frames when an
unexpected exception occurs. The SDK's own errors strip internal frames, so only bugs expose
this. `ClientConfig`'s `repr` includes `default_headers`, which is where a caller would put their
own secret header, such as a proxy key. The public objects are all fine: the client's `repr`,
`HttpRequest` and `CreatedInstance.password` hide their secrets.

**Suggested fix:** `access_token: str = field(repr=False)` on `_Token`, and `repr=False` on
`ClientConfig.default_headers`.

## 5. Redirects from HTTPS to HTTP are followed (Low)

**Status:** Open.

**Where:** `src/aura_python_sdk/_internal/http/_httpx.py:55` (`follow_redirects=True`)

**Problem:** httpx drops `Authorization` on every origin change, and I confirmed this for
cross-host, cross-port, subdomain and HTTPS-to-HTTP redirects. But it still *follows* a redirect
to `http://`. The rest of the request goes out in cleartext, including a `POST` body on a
307 or 308, and the SDK then trusts a response that anyone on the network path could have
changed. It would take a misconfigured or compromised Aura endpoint to issue such a redirect,
hence Low. It does undo the HTTPS-only guarantee the SDK enforces for `base_url`.

**Suggested fix:** refuse redirects that leave HTTPS unless `allow_insecure_base_url` is set.
For example, follow redirects manually with a limit, or check `response.next_request.url.scheme`
in an httpx event hook, and raise `AuraConnectionError` otherwise.

## 6. Deeply nested JSON raises `RecursionError`, not an SDK error (Low)

**Status:** Open.

**Where:** `src/aura_python_sdk/_internal/_request.py:30` (`ApiResponse.json`)

**Problem:** a response body of `[[[[…]]]]` 200,000 levels deep, well under the 10 MB limit,
makes `json.loads` raise `RecursionError`. `ApiResponse.json` catches only `ValueError`, so the
`RecursionError` gets past `except AuraError`. Only the Aura API itself could send this, since
Prometheus responses go through the text parser instead.

**Suggested fix:** catch `RecursionError` there too, and raise `AuraResponseError`.

## 7. `allow_insecure_base_url` also turns off the Prometheus allowlist (Info)

**Status:** Open.

**Where:** `src/aura_python_sdk/_client.py`, where `allow_untrusted_urls` comes from
`allow_insecure_base_url`

It's documented, but it's one flag doing two jobs. Someone who turns it on to test against a
local API server also lets the SDK send the bearer token to any metrics URL. Consider a separate
`allow_untrusted_metrics_urls` option, or document the consequence where the flag is described.

---

## Done well

- **The Prometheus allowlist is resistant to parser confusion.** Of 25 URLs built to trick it
  (backslashes, userinfo, `%23`, `%2F`, `%00`, tabs, full-width dots, uppercase letters,
  trailing dots, `evilneo4j.io`), every one it accepted resolves in httpx to a host under
  `neo4j.io`.

- **The token isn't sent across redirects.** httpx drops `Authorization` on any change of host,
  scheme or port. I confirmed this with a mock network.

- **Nothing sensitive is logged.** I ran every path at DEBUG level: token fetch, a 401 and token
  refresh, a 503 retry, a network error, `with_options`, and rejected credentials. That
  produced 35 records. None of them, nor the exception text or the client's `repr`, contains the
  secret, the Basic credentials or either token.

- **Transport security.** HTTPS is enforced for `base_url`, certificates are verified, TLS 1.2 is
  the minimum, and `.netrc` has no effect.

- **Injection.** Path segments are percent-encoded, instance, tenant and snapshot IDs are
  format-validated, and CR/LF in `user_agent` or `default_headers` is rejected.

- **Untrusted responses.** The size limit applies to the decompressed stream, and the Prometheus
  parser runs in linear time (a 9 MB label value parses in 0.5 s).

- **Retries never repeat a write** that might already have reached the server.
- **CI and release workflows.** Permissions are read-only by default, neither workflow uses
  `pull_request_target`, OIDC trusted publishing means no stored token, and the `testpypi`
  environment only allows `v*` tags.

- **Dependencies.** `pip-audit` found no known vulnerabilities in the locked dependencies
  (httpx 0.28.1, httpcore 1.0.9, h11 0.16.0, certifi 2026.7.22 and the rest).

- **Secrets in the repo.** `.env` is gitignored, and the real tenant ID has never been committed.

## Not checked

- The Aura API's own behaviour, such as whether it rejects `DELETE /v1`.
- Custom transports that callers write. The SDK can't control their redirect or TLS handling.
- A line-by-line audit of httpx and its dependencies, beyond the vulnerability database.
