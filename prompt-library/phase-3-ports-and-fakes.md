# Phase 3 — Ports, in-memory adapter, contract suite

**Goal:** the persistence interface, a complete in-memory implementation, and the
contract suite that will later prove the Notion adapter correct.

**Depends on:** Phase 2. Still no network.

The contract suite is the most valuable artifact in this phase. It is what makes
the in-memory adapter trustworthy as a test double for every later test, and it is
the concrete meaning of "we could swap the database."

## 3.1 `ports/repositories.py`

Two ABCs, exactly as in `02-architecture.md` §Repository. Methods take and return
**domain entities**. No Notion dicts, no `dict[str, Any]`, no property names.

`full_body` is a separate parameter on `add` and `update` rather than a field on
`Post`, because the entity carries the preview and a flag while the full text is a
lazily-fetched detail. Keeping it off the entity is what structurally prevents the
feed from loading bodies.

Segregate the two repositories even though one unit of work supplies both, so a
use case that only reads books cannot reach posts.

## 3.2 `ports/unit_of_work.py`

```python
class UnitOfWork(ABC):
    books: BookRepository
    posts: PostRepository
    async def __aenter__(self) -> "UnitOfWork"
    async def __aexit__(self, exc_type, exc, tb) -> None
    async def commit(self) -> None
    async def rollback(self) -> None
```

`__aexit__` rolls back when an exception passed through and does nothing
otherwise. It does **not** auto-commit — an implicit commit on a use case that
returned `Err` is a bug waiting to happen. Use cases commit explicitly.

Write the docstring now, and say plainly that a given implementation may provide
compensating rollback rather than atomicity. Phase 4 depends on that expectation
having been set here.

## 3.3 `adapters/memory/`

`InMemoryBookRepository`, `InMemoryPostRepository`, `InMemoryUnitOfWork`.

State lives in dicts on the unit of work; the repositories hold references to it.
`__aenter__` deep-copies the state as a snapshot; `rollback()` restores it;
`commit()` discards the snapshot. That gives real transactional semantics, which is
what makes the fake a strict superset of Notion's behaviour rather than a
different one.

Store archived posts with an `archived` flag rather than deleting them, and filter
them out of `list_for_book`. Notion behaves that way, and a fake that hard-deletes
would let a bug through.

`add` assigns a UUID id and a `created_at` from an injected clock — pass a
`Callable[[], datetime]` into the constructor, defaulting to `datetime.now`. Tests
that assert on ordering need control of time, and a hidden `now()` call is the
usual reason those tests turn flaky.

## 3.4 `tests/builders.py`

```python
def make_book(**overrides) -> Book
def make_post(**overrides) -> Post
def make_progress(member, chapter, page=None, **overrides) -> Post
def make_reply(parent, member, **overrides) -> Post
```

Every field defaulted, so a test states only what it cares about. `make_reply`
copies the parent's position and sets `parent_post_id` and `type` — the rule lives
in one place in the tests, mirroring the use case that will enforce it in Phase 5.

## 3.5 The contract suite

`tests/contract/test_unit_of_work_contract.py`. An abstract class holding the
tests and an unimplemented `uow` fixture, subclassed once per implementation. This
phase adds the in-memory subclass; Phase 4 adds the Notion one and must not modify
the contract.

Books:

```
test_added_book_is_retrievable_by_id
test_added_book_appears_in_list_all
test_get_returns_none_for_unknown_book_id
test_updated_book_reflects_new_values
test_list_all_returns_books_from_an_empty_store_as_empty_list
```

Posts:

```
test_added_post_is_retrievable_by_id
test_posts_are_listed_only_for_their_own_book
test_archived_post_is_not_listed
test_archived_post_is_still_retrievable_by_id
test_reply_is_listed_alongside_top_level_posts
test_short_post_reports_has_full_body_false
test_long_post_reports_has_full_body_true
test_full_body_round_trips_above_1900_characters
test_get_full_body_on_a_short_post_returns_the_preview
test_updating_a_post_from_long_to_short_removes_the_full_body
test_updating_a_post_from_short_to_long_stores_a_full_body
test_updating_a_long_post_replaces_rather_than_appends_the_full_body
```

The last three are the ones that catch real bugs. The short→long→short transitions
are where the Notion adapter has to create, update, and delete a block, and where
an implementation that only handles the common case passes every other test.

Transactional behaviour:

```
test_rollback_discards_an_added_post
test_rollback_discards_an_update
test_rollback_restores_an_archived_post
test_commit_persists_across_a_new_unit_of_work
```

Mark the first three `@pytest.mark.fake_only` when the Notion subclass runs them,
with the reason string *"Notion has no transactions; rollback is compensating and
is covered by the compensation tests in Phase 4."* Two fake-only markers are
expected across the suite. A third should prompt a design conversation rather than
another marker.

## 3.6 Guard the fake

One test that is not part of the contract:

```
test_in_memory_repositories_implement_every_abstract_method
```

Walk the ABCs and assert no method resolves to the abstract version. A port method
added in a later phase and never implemented on the fake would otherwise surface as
a confusing failure inside an unrelated application test.

## Acceptance checks

- [ ] The full contract suite passes against `InMemoryUnitOfWork`
- [ ] Exactly two tests carry `fake_only`, each with a reason string
- [ ] The in-memory adapter has no dependency on `httpx` or Notion
- [ ] `app/adapters/memory` is at 100% coverage — it is pure and there is no excuse
- [ ] Builders default every field; no test sets a field it does not assert on
- [ ] `pytest tests/unit tests/contract` still runs in under two seconds
