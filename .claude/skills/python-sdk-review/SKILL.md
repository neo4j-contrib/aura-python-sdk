---
name: python-sdk-review
description: Review a Python SDK or client library's public API surface against Python and SDK design best practice (PEP 8/257/484/561, the Azure SDK for Python guidelines, and patterns from httpx, stripe-python and openai-python), and produce a ranked, evidence-backed findings report. Use this whenever someone asks to review, audit or sanity-check a Python SDK, client library, API wrapper or package's public interface, exports, naming, typing, errors, sync/async design, pagination, retries, models or versioning; or asks "is this Pythonic", "what would a user of this library trip over" or "is this ready to publish", even if they don't say "SDK". Not for hunting bugs in a diff (use code-review) or for non-Python code.
---

# Python SDK surface review

The goal is to judge the library the way its *callers* will experience it: what they can import,
what they have to type, what they get back, what gets raised, and what breaks when they upgrade.
Internal implementation quality matters only where it leaks through the public surface.

Work read-only. Don't change code during the review: the person needs to see and rank the
findings before anything is fixed, and some findings are deliberate trade-offs they'll want
to keep.

## Workflow

### 1. Map the public surface

Before judging anything, establish what "public" means in this package, because every later
finding depends on it.

- Read `pyproject.toml`: the package name, `requires-python`, dependencies, build backend and
  any `py.typed` marker.
- Read the top-level `__init__.py` and `__all__`. List every exported name and where it comes
  from.
- Note the privacy convention (for example `_internal/`, leading-underscore modules) and check
  it's applied consistently: can a user reach something they shouldn't, or do they have to
  import from a private module to do something normal (type-annotate a return value, catch an
  error, write a fake transport)?
- Read the README and examples. They show the intended usage, and a gap between the docs and
  the code is a finding in itself.
- Skim the tests only to learn intended behaviour. Don't review the tests.

For packages over about 5k lines, give an Explore agent the mapping step and ask for
the list of exported names with file:line locations, then read the key files yourself. The
judgement calls need the actual code in front of you.

### 2. Walk the checklist

Read `references/checklist.md` and go through every section in order. It lists what to check
and why each item matters to a caller. Not every item applies to every SDK. Skip the
inapplicable ones silently rather than padding the report.

Verify each candidate finding against the code before writing it down. Open the file, find the
line, and make sure the problem is real and reachable from the public API. Check whether it's
already documented as a deliberate choice (README, docstring, comment, CHANGELOG). If it is,
either drop it or report it as "consider" with the stated reason, and give your
counter-argument if you have one.

Where you can, confirm behaviour by running it rather than by reading alone. For example:
`python -c "import pkg; print(pkg.__all__)"`, calling `help()` on an object, running
`mypy --strict` over a small snippet written the way a caller would, or checking that a model
really is frozen. Running it is the quickest way to rule out a false positive.

### 3. Rank and write the report

Put each finding into one of three tiers. Ask yourself: *what does this cost a caller, and
does fixing it later break them?*

- **Must fix**: callers get wrong behaviour, lose type safety, or can't do something normal
  without reaching into private code. Also anything that will become a breaking change once
  there are users (naming, positional parameters, exception hierarchy, what's exported), so
  it's cheapest to fix before the first stable release.
- **Should fix**: real friction or inconsistency with an easy, compatible fix.
- **Consider**: a judgement call, or a trade-off where reasonable SDKs differ. Give both sides.

Also list what the SDK does *well*. That keeps the review calibrated, and it tells the
person what not to "fix".

## Report format

Use this structure. Save it as a Markdown file (in the scratchpad directory if there is one,
unless the person names a location), and give a short summary plus the path in the
conversation.

```markdown
# <package> public API review

**Scope:** <version or commit>, public surface as exported from `<pkg>/__init__.py`.
**Summary:** <2–3 sentences: overall state, and the handful of things that matter most.>

## Must fix
### 1. <Short claim, e.g. "Services accept required arguments positionally">
**Where:** `src/pkg/services/x.py:42` (and N similar)
**Problem:** what a caller experiences, with a 2–5 line snippet of the caller's code if that
makes it clearer.
**Why it matters:** the guideline or precedent, and the cost of leaving it.
**Suggested fix:** concrete and minimal. Say if it's breaking.

## Should fix
...

## Consider
...

## Done well
- <bullet per strength, with a file reference>

## Not checked
<anything out of scope or not verifiable, e.g. "live API behaviour">
```

Number findings continuously across tiers so they can be referred to as "#7". Group repeated
instances of one problem into a single finding with a count and the locations, rather than
listing each one separately.

Keep claims precise. "`list()` returns `list[Instance]` and loads every page into memory" is
useful. "Pagination could be improved" isn't.
