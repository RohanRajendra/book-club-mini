# Spec deltas

`prompt-library/` is the specification and is never edited. This file records every
place the build deliberately diverges from it, why, and which file the divergence
amends. Each entry states the contradiction as found, so a reader can check the
reasoning rather than trusting it.

The rule from `02-architecture.md` — *every abstraction traceable to a stated
requirement* — applies here too: a delta with no contradiction behind it is not a
delta, it is drift.

---

## D1 — `fake_only` marker count is three, not two

**Amends:** `phase-3-ports-and-fakes.md` §3.5 + acceptance,
`phase-4-notion-adapter.md` §4.7 + acceptance, `03-testing-strategy.md` §Contract.

**Contradiction.** `phase-3` §3.5 instructs: "Mark the first three
`@pytest.mark.fake_only`". Its own acceptance check requires "Exactly two tests
carry `fake_only`". `phase-4` repeats "Still exactly two". `03` says "Two are
expected: true rollback semantics, and ordering guarantees" — naming a category
(ordering) that is not among the three transactional tests.

**Resolution.** Three markers, on the three tests `phase-3` actually names:

| Test | Reason string |
|---|---|
| `test_rollback_discards_an_added_post` | Notion has no transactions; rollback is compensating |
| `test_rollback_discards_an_update` | same |
| `test_rollback_restores_an_archived_post` | same |

All three share one root cause, so they are one design fact, not three. `03`'s
"ordering guarantees" marker is **not** created — no contract test currently
depends on ordering the two adapters disagree about. If one appears, that is the
design conversation `03` asks for.

`test_commit_persists_across_a_new_unit_of_work` stays unmarked: it passes against
both implementations.

---

## D2 — A feed load costs one *query*, plus one book read

**Amends:** `00-overview.md` §Notion facts, `phase-6-http-api.md` §6.7 +
acceptance.

**Contradiction.** Three files assert a feed request costs exactly one outbound
Notion request. `phase-5` §5.5 requires `GetFeed` to return the book as well as
the posts, and `ScaleCalculator` needs the book's `total_chapters`. Reading the
book is a second request. Separately, pagination past 100 posts costs one request
per cursor page, up to the 5-page cap.

**Resolution.** The invariant becomes: **one data-source query per feed load, plus
at most one book read, and no per-post requests.** The per-post clause is what the
original claim was actually protecting — it is the property that breaks under the
rate limit — and it is preserved exactly.

The Phase 6 test asserts the post query happens exactly once and that no request
is issued per post. The book read is served from the container's `ListBooks` cache
when warm, so the steady-state cost stays at one.

---

## D3 — Type filtering is client-side

**Amends:** `phase-6-http-api.md` §6.3, `phase-7-frontend.md` §7.4.

**Contradiction.** `01-ux-spec.md` §4 requires four filter chips *each showing a
count*. `phase-6` puts the filter on the server as `?type=`, and `phase-7` has
`test_use_feed_refetches_when_the_filter_changes`. A server that filters cannot
report counts for the types it filtered out, so the chips cannot render.

**Resolution.** The feed always returns every post for the book; the chips filter
in the browser. `01-ux-spec.md` wins per its own precedence rule ("Where a phase
file and this file disagree, this file wins").

Consequences:

- `?type=` remains implemented on `GET /api/books/{id}/feed` and remains tested —
  it is a legitimate API capability — but the UI never sends it.
- `useFeed` does **not** refetch on filter change. `phase-7`'s
  `test_use_feed_refetches_when_the_filter_changes` is replaced by
  `test_use_feed_does_not_refetch_when_the_filter_changes`, which is the stronger
  assertion: a chip click must cost zero requests.
- The cache key keeps its filter component (a `?type=` caller still gets correct
  caching), so nothing in `phase-5` §5.8 changes.
- `FeedAssembler` still implements filtering, and every `phase-5` filter test
  stands unchanged — the capability moves consumers, not layers.

---

## D4 — The feed cache key includes the viewer

**Amends:** `02-architecture.md` §Decorator, `phase-5-application-services.md`
§5.8 opening.

**Contradiction.** `02` and the first line of `phase-5` §5.8 say the cache is
"keyed by book and filter". `phase-5`'s own final test
(`test_the_cache_is_bypassed_for_a_different_viewer`) and `phase-6` §6.3 both
require the viewer in the key.

**Resolution.** The key is `(book_id, filter, viewer)`. Spoiler flags are computed
per viewer, so a key without the viewer serves one member's blur state to the
other through the **View as** control. The two "book and filter" sentences are
incomplete, not a competing design.

---

## D5 — Use cases validate; entity `__post_init__` guards are assertions

**Amends:** `02-architecture.md` §Result, `phase-2-domain-core.md` §2.4.

**Contradiction.** `02` reserves exceptions for "genuine faults: network failure,
misconfiguration, bugs", and requires every use case to return `Result` for
expected failures. But `phase-2` specifies entities that *raise* on invalid input
(`test_book_rejects_blank_title`,
`test_position_rejects_zero_or_negative_chapter`). A blank title arriving from a
form is an expected failure, and `AddBook` must return `Err(TitleRequired)` for
it. The spec never says which layer owns the check.

**Resolution.** Both, with different jobs:

- **Use cases validate first** and return `Err(...)` before constructing anything.
  This is the path real input takes, and it is where the `Result` contract lives.
- **Entity guards stay** and raise `ValueError`. They are last-line assertions
  against a programming error — an entity constructed wrongly inside the codebase
  — not input validation. They are covered by direct unit tests on the entity.

This is deliberate duplication of a *check*, not of a *rule*: the rule (a book
needs a title) is expressed once as a predicate in the domain and used by both.

**Coverage note.** Both layers are under a 100% branch gate, and both sides are
directly tested, so the gate is satisfied without contortion.

---

## D6 — `ScaleCalculator` when the observed chapter exceeds a stated total

**Amends:** `phase-2-domain-core.md` §2.6.

**Contradiction.** `test_scale_uses_total_chapters_when_known`,
`test_scale_is_not_estimated_when_total_chapters_known` and
`test_scale_never_falls_below_the_highest_observed_chapter` (worked example:
total 30, observed 400) cannot all hold. The spec states the requirement — "the
scale must still contain the post" — but not what `is_estimated` becomes.

**Resolution.**

```
max_chapter  = max(total_chapters, highest_observed)      when total is known
             = max(ceil(highest_observed * 1.2), 10)      when total is unknown
is_estimated = total_chapters is None
```

`is_estimated` tracks *whether the book told us its length*, not whether the
number was adjusted. A book with a stated total is not an estimate even when a
post overshoots it; the overshoot is a data error in Notion, and the spine's job
is to stay honest about the source, not to relabel itself. No headroom is added
when the total is known — the true end of the book is a fact worth showing.

Added test: `test_scale_extends_past_a_stated_total_without_becoming_estimated`.

---

## D7 — `UnitOfWork` gains an `on_commit` hook

**Amends:** `02-architecture.md` §Unit of work + §Decorator,
`phase-3-ports-and-fakes.md` §3.2, `phase-5-application-services.md` §5.8.

**Gap.** `02` and `phase-5` both require cache invalidation to happen in exactly
one place, hooked to successful commit. The `UnitOfWork` port as specified has no
callback, `application/` may not import `adapters/` (architecture-tested), and no
file adds the seam. As written the requirement is unimplementable.

**Resolution.** The port grows one member:

```python
class UnitOfWork(ABC):
    on_commit: list[Callable[[], None]]
```

`commit()` invokes each callback after the write path succeeds, and only then.
The container registers `CachingFeedQuery.invalidate` when it builds a unit of
work. Both adapters honour it and the contract suite tests it, so it is a port
behaviour rather than an adapter convenience.

**Justification, in `02`'s own terms.** It serves the testability requirement:
without it, invalidation must be called at every write site, and "did this use
case invalidate the cache" becomes an assertion repeated in eight use-case test
modules instead of one contract test. It also survives a database swap unchanged.

Contract tests added: `test_on_commit_callbacks_run_after_a_successful_commit`,
`test_on_commit_callbacks_do_not_run_after_a_rollback`.

Also recorded in `docs/decisions.md`, per `02`'s rule for added patterns.

---

## D8 — ID wrappers are frozen dataclasses, not `NewType`

**Amends:** `phase-2-domain-core.md` §2.3.

**Contradiction.** The stated justification is that the wrappers "stop the
argument-order bug where a book ID lands in a post ID parameter". `NewType` is
erased at runtime and `02` §Dependencies forbids mypy, so nothing would catch that
bug — the justification describes a benefit the project has ruled out.

**Resolution.** `MemberName`, `BookId` and `PostId` are frozen single-field
dataclasses with `__post_init__` rejecting empty values. The stated benefit then
actually exists: passing a `BookId` where a `PostId` belongs raises at the
boundary, at runtime, with no type checker. They also gain a `__str__` so mapper
and log call sites stay readable.

---

## D9 — Unsaved entities carry no ID

**Amends:** `02-architecture.md` §Repository, `phase-2-domain-core.md` §2.4.

**Gap.** `PostRepository.add(post: Post, full_body)` takes a fully-formed `Post`,
but `Post` carries `id`, `created_at` and `edited_at` — none of which exist before
the write. The spec never says what a use case passes.

**Resolution.** On `Book` and `Post`, `id`, `created_at` and `edited_at` are
`| None` and default to `None`. `add()` returns a new instance with all three
populated by the store. Every other field keeps its invariants, so an unsaved
entity is still a validated entity.

Rejected alternative: a separate `NewPost` draft type. It doubles the entity
count and every mapper, to encode a distinction that one nullable field already
carries.

Added tests: `test_an_unsaved_post_has_no_id`,
`test_add_returns_a_post_with_an_id_and_created_at` (contract suite, both
adapters).

---

## D10 — `was_edited` uses a 60-second threshold

**Amends:** `01-ux-spec.md` §5 (making "meaningfully" concrete),
`phase-2-domain-core.md` §2.4.

**Gap.** `01-ux` shows the `edited` marker when `last_edited_time` "differs
meaningfully" from `created_time`; `phase-2` tests exact equality
(`test_post_was_edited_is_false_when_timestamps_match`). Neither survives contact
with the write path: creating a post over 1900 characters is a page create
**followed by** a block append, and the append bumps the page's
`last_edited_time`. Every long post would be born showing `edited`.

**Resolution.** `Post.was_edited` is `(edited_at - created_at) > 60 seconds`. The
threshold is one module-level constant in `domain/entities.py`.

Sixty seconds is chosen against the failure it prevents: the create-then-append
pair completes in well under a second even with the rate limiter, while a genuine
edit requires a human to read the post, click Edit, and type — which does not
happen inside a minute. The window is wide enough to absorb Notion's
second-resolution timestamps and clock skew between the two installations.

`test_post_was_edited_is_false_when_timestamps_match` is kept and joined by
`test_post_was_edited_is_false_for_a_create_then_block_append`.

---

## D11 — `GetPostBody` test renamed

**Amends:** `phase-5-application-services.md` §5.7.

**Contradiction.** `test_does_not_call_the_repository_when_has_full_body_is_false`
describes something impossible: the use case must call `posts.get` to *learn*
`has_full_body`. Built to the name, the use case cannot work.

**Resolution.** Renamed to
`test_does_not_call_get_full_body_when_has_full_body_is_false`, which is the
assertion §5.7 is actually making — that the preview/full-body split saves a
request. Verified against the in-memory repository's call log, not a mock, as
§5.7 requires.

---

## D12 — `fake_only` skip machinery

**Amends:** `phase-1-notion-and-scaffold.md` §1.3.

**Gap.** `phase-1` registers the `fake_only` marker so `--strict-markers` passes,
and nothing more. But the marker sits on the shared abstract contract class, so it
applies to *both* subclasses — including the in-memory one it is meant to let
through. Registration alone skips nothing.

**Resolution.** A `pytest_collection_modifyitems` hook in
`backend/tests/conftest.py` skips a `fake_only` test only when the test class
declares `supports_transactions = False`. `TestNotionUnitOfWork` sets it;
`TestInMemoryUnitOfWork` does not.

Keying on a declared capability rather than a class name means a future SQLite
adapter with real transactions runs those three tests automatically, which is
exactly the swappability claim `phase-8` §8.7 makes.

---

## D13 — Roster is prompted for, and its order matters

**Amends:** `phase-8-polish-and-handoff.md` §8.1 step 3.

**Gap.** `setup.sh` is specified to prompt for `NOTION_TOKEN`, `MEMBER_NAME` and
the two database IDs. `MEMBERS` is a required setting (`02` §Configuration) and
startup fails without it, so the second installation cannot start.

**Resolution.** `setup.sh` prompts for `MEMBERS` too, and prints that **both
installations must list the members in the same order** — reader colours are
assigned by roster index (`01-ux` §Visual direction), so a swapped order swaps the
two members' colours between machines and breaks the wayfinding the colour system
exists for.

---

## D14 — Coverage gates run as a script, not one `pytest` flag

**Amends:** `03-testing-strategy.md` §Coverage targets + §Running.

**Contradiction.** `03` requires four different thresholds (100% on `domain` and
`application`, ≥90% on `adapters` and `interface`) and, in §Running, "One `pytest`
invocation". `pytest-cov` accepts a single global `--cov-fail-under`, so the two
cannot both hold.

**Resolution.** `pytest` alone still runs the whole suite and still collects
coverage — the developer loop `03` cares about is untouched. The gate is one
extra command, `backend/scripts/check_coverage.py`, which reads the coverage data
`pytest` already wrote and applies the per-package thresholds from the table.

No new dependency: it uses `coverage`, which `pytest-cov` already installs.

---

## D15 — API tests attach the container explicitly

**Amends:** `phase-6-http-api.md` §6.1, §6.5.

**Gap.** `httpx.ASGITransport` does not run ASGI lifespan events, so the container
`main.py` builds in the lifespan handler is never created in Phase 6's API tests
and `app.state.container` is unset. Related:
`test_health_reports_both_data_source_ids` cannot pass against an in-memory
container, which has no data source IDs to report.

**Resolution.** The API test fixture builds an in-memory container and assigns
`app.state.container` directly before the request — which is exactly the
capability `test_a_test_container_can_be_built_with_in_memory_adapters_and_no_http`
exists to prove, so the container's stated job is what makes the tests possible.

`/api/health` reports data source IDs when they are configured and `null` when
running on in-memory adapters. The API test asserts the shape; the live check in
`phase-6`'s acceptance list asserts the real IDs.

---

## D16 — Repository layout

**Amends:** `phase-1-notion-and-scaffold.md` §1.3.

The tree in `phase-1` is rooted at a folder named `bookclub/`. This repository is
`book-club-mini`, so `backend/`, `frontend/`, `docs/`, `dev.sh` and `setup.sh` sit
at the repository root. The structure below that point is unchanged.

**Also:** the repository's existing `.gitignore` ignores `lib/`, which would
silently exclude `frontend/src/lib/` — the entire pure-helper directory
`phase-7` §7.3 specifies. A `!frontend/src/lib/` negation is added in the same
commit as the scaffold.

---

## Not changed, though tempting

- **`UnknownMember` is kept** despite being unreachable in production: posts are
  always attributed to `MEMBER_NAME`, which `Settings` validates against `MEMBERS`
  at startup. `phase-5`'s acceptance rule ("returned by at least one use case, or
  deleted") is met by `CreatePost`. Deleting it would move the check to a bare
  `assert` and lose the 400 that a misconfigured caller deserves.
- **The Notion contract suite runs against our own stub** (`phase-4` §4.7). That
  proves conformance to our model of Notion, not to Notion. Left as designed — the
  scratch-script acceptance check in §4.7 is what closes the gap, and it is not
  skipped.
