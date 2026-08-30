# Pattern register

One entry per pattern in `prompt-library/02-architecture.md`: what it is, the
requirement that justified it, and what would have to change for it to be
removed.

This file exists to stop the next person from either ripping out abstractions
that are load-bearing or adding more by pattern-matching. The rule from `02`
holds: **every abstraction must be traceable to a stated requirement** — either
testability, or the goal of being able to swap Notion for another database. One
that serves neither is ceremony.

Divergences from the specification are recorded separately, in
[spec-deltas.md](spec-deltas.md).

---

## Repository — `app/ports/repositories.py`

**What.** Two ABCs, `BookRepository` and `PostRepository`, taking and returning
domain entities. Notion's property shapes stop at the mapper.

**Justified by.** The database-swap goal, and it is what lets every application
test run against an in-memory fake instead of HTTP. Phase 5's 92 tests touch no
network because of this one seam.

**Removable when.** Never, while there is more than one implementation. If the
Notion adapter became the only one and swapping were abandoned, the ports could
collapse into it — at the cost of every application test needing `respx`.

**Note.** `full_body` is a parameter rather than a field on `Post` because the
entity carries the preview and a flag; the full text is a lazily-fetched detail.
Keeping it off the entity is what structurally prevents the feed from loading
bodies, and `GetPostBody`'s call-log test is what proves it.

---

## Unit of work — `app/ports/unit_of_work.py`

**What.** A scope over both repositories with explicit `commit()` and
`rollback()`. `__aexit__` rolls back on an exception and never auto-commits.

**Justified by.** Two operations are multi-step and must not half-apply:
creating a long post (page, then block) and deleting a post (post, then each
reply). It is also the correct seam for a future SQLite adapter.

**Removable when.** Both of those become single writes. Neither will.

**Note.** `NotionUnitOfWork.rollback()` is **compensating, not atomic** — Notion
has no transactions. It replays inverse operations, best-effort. A compensation
can fail, and a concurrent reader can see an intermediate state. Both are
acceptable for two people and both are in the README.

---

## `on_commit` hook — added, not in `02`

**What.** `UnitOfWork.on_commit: list[Callable[[], None]]`, fired after a
successful commit and never after a rollback. The container registers the feed
cache's `invalidate`.

**Justified by.** `02` and `phase-5` both require cache invalidation to happen in
exactly one place, hooked to successful commit — but the port as specified had
no seam for it, and `application/` may not import `adapters/`. Without this the
requirement is unimplementable, and invalidation has to be repeated at eight
write sites with a matching assertion in eight test modules.

**Removable when.** The cache is removed, or something else takes ownership of
invalidation. It is contract-tested against both adapters, so a third adapter
gets it for free.

Recorded as delta D7.

---

## Result objects — `app/domain/result.py`

**What.** Frozen generic `Ok`/`Err`, with `is_ok`, `unwrap`, `unwrap_err`, `map`.
Every use case returns one.

**Justified by.** Use cases have expected failures — a missing book, a reply to a
reply, an oversized body. Exceptions for expected outcomes make TDD assertions
awkward and hide the failure set from the signature.

**Removable when.** Never, cheaply — the interface layer's error table and an
architecture test both depend on it.

**Note.** `DomainError` is deliberately **not** an exception, so raising one is
impossible and the only way to signal an expected failure is to return it.
Entity guards raise `ValueError` instead, and those are last-line assertions
against a programming error, not input validation (delta D5).

**Not added.** `and_then`, `or_else` and the rest of the combinator family.
Nothing has needed them.

---

## Strategy — `app/domain/policies.py`

**What.** `SpoilerPolicy` ABC with one method; `ChapterFirstSpoilerPolicy` the
only implementation.

**Justified by.** The blur rule is the single most likely thing in this app to
change, and isolating it makes it exhaustively unit-testable without
constructing a feed. Twelve tests cover it and none of them build a `Feed`.

**Removable when.** The blur rule is deleted. A *percent-based* rule is a new
class, not an `if` in this one — that is the open/closed case the pattern is
here for.

**Note.** It delegates ordering to `Position.is_ahead_of` rather than
reimplementing it. Two copies of the ordering rule is how they drift, and a test
asserts the delegation.

---

## Mapper — `app/adapters/notion/mappers.py`

**What.** `BookMapper` and `PostMapper`, `to_domain` / `to_properties`. Property
names are module-level constants and appear nowhere else.

**Justified by.** Notion property names are the most fragile knowledge in the
codebase. One class per entity keeps it in one place and lets mapping be tested
against recorded fixtures with no HTTP.

**Removable when.** Notion is gone.

**Note.** `to_domain` is forgiving by design: an unrecognised status becomes
`Upcoming`, a `Progress` row with its chapter cleared degrades to `Thought`. The
owner edits these rows by hand and a hand-edit must not 500 the feed. This
earned itself immediately — the live workspace had the relation named `Books`,
Notion's default, and one constant was the whole fix.

---

## Decorator — `app/application/caching.py`

**What.** `CachingFeedQuery` implements the same interface as `GetFeed` and wraps
an instance of it. 20-second TTL, keyed by book, viewer and filter.

**Justified by.** Caching is orthogonal to feed assembly. Wrapping keeps
`FeedAssembler` free of cache concerns and lets every assembler test run without
cache interference.

**Removable when.** The refresh model changes. Twenty seconds is tuned to it: the
frontend refreshes on window focus, so alt-tabbing back repeatedly must not fire
a Notion query each time. Measured live at 0 requests for a cached load.

**Note.** The key includes the **viewer** because spoiler flags are
viewer-specific; without it the *View as* control serves one member's blur state
to the other (delta D4).

---

## Composition root — `app/composition.py`

**What.** A hand-written `Container`, ~120 explicit lines. Not
`dependency-injector`.

**Justified by.** The object graph must be constructible from HTTP handlers, from
tests, and from scripts. FastAPI's `Depends` covers only the first. The live
verification script and the whole API test suite both build one directly.

**Removable when.** Never, while tests build the graph. Its `uow_factory`
parameter is the seam that makes an in-memory container possible, and
`ASGITransport` not running lifespan means the API tests depend on it (delta
D15).

**Not added.** A DI framework. String-keyed provider wiring reads worse than the
explicit constructor calls, and the wiring is the part a newcomer most needs to
read.

---

## Contract suite — `backend/tests/contract/`

**What.** One abstract test class, subclassed once per port implementation.

**Justified by.** It is the Liskov check for the whole port design and what makes
the in-memory adapter trustworthy as a test double for every later test.

**Removable when.** There is one implementation and no intent to add another.

**Note.** It passed against `NotionUnitOfWork` on the first run, which is the
strongest evidence available that the ports describe persistence rather than
describing the fake. Three tests carry `fake_only` (delta D1); the marker is
keyed on a declared `supports_transactions` capability, so a SQLite adapter with
real transactions would run them automatically.

---

## Deliberately not added

- **A DI framework**, an ORM, a task queue, Redis, Docker, mypy, a linter config.
- **`notion-client`** — its support for `2025-09-03` lags, and the adapter is a
  thin wrapper over `httpx` with no version ambiguity.
- **Tailwind or a component library** — the token system is small and
  hand-written on purpose, and a utility framework pulls a design toward the
  defaults it ships with.
- **A frontend router or state manager** — one screen, and all state lives in
  five hooks.
- **Component tests** — not a coverage compromise but the constraint the frontend
  is designed around: if a component holds something worth testing, that thing is
  in the wrong place.
