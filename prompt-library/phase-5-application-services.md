# Phase 5 — Application services

**Goal:** every use case in the app, tested against the in-memory adapter, with no
HTTP anywhere in this phase's tests.

**Depends on:** Phases 2–4. This phase is where the business rules that need more
than one object finally live.

Every use case is a class with a single `execute` method, receives its
collaborators through **constructor injection only**, and returns `Result`. No
module-level singletons, no service locator, no importing the container.

## 5.1 Use case inventory

```
application/use_cases/
├── list_books.py        ListBooks
├── add_book.py          AddBook
├── update_book.py       UpdateBook
├── get_feed.py          GetFeed
├── create_post.py       CreatePost
├── edit_post.py         EditPost
├── delete_post.py       DeletePost
└── get_post_body.py     GetPostBody
```

## 5.2 `CreatePost`

The most rule-dense object in the app. Tests before code:

```
test_creates_a_thought_with_a_position
test_creates_a_progress_post_with_no_body
test_progress_without_a_chapter_returns_chapter_required_error
test_page_without_a_chapter_returns_page_requires_chapter_error
test_thought_without_a_body_returns_body_required_error
test_thought_without_a_chapter_is_accepted
test_body_over_the_limit_returns_body_too_long_error
test_unknown_book_returns_book_not_found
test_member_not_in_roster_returns_unknown_member
test_reply_forces_type_to_reply
test_reply_copies_the_parents_position_ignoring_any_supplied
test_reply_to_a_reply_returns_cannot_reply_to_reply
test_reply_to_a_post_in_another_book_returns_reply_book_mismatch
test_reply_to_a_missing_parent_returns_post_not_found
test_long_body_is_split_into_preview_and_full_body
test_successful_creation_commits_the_unit_of_work
test_a_failed_validation_does_not_write_anything
```

Rules worth restating, since each is a decision from `01-ux-spec.md`:

- A `Progress` post requires a chapter. That is what makes it a progress update.
- `Thought` and `Question` accept no chapter. Such a post can never be blurred for
  anyone; that is the member's choice and the app does not warn.
- A page without a chapter is rejected — a page number alone cannot be compared
  against anyone's position.
- A reply's `type` is forced to `Reply` and its position is **copied from the
  parent**, overwriting anything the caller sent. Copying rather than joining is
  what keeps spoiler evaluation free of lookups.
- Replies are flat: replying to a reply is an error, not a silent re-parent.

Position pre-filling for thoughts and questions is a **frontend** concern, not
this use case's. The API takes what it is given. Putting the default here would
make it impossible for a member to deliberately post without a position.

## 5.3 `EditPost`

```
test_owner_can_edit_their_own_post
test_non_owner_returns_not_post_owner
test_missing_post_returns_post_not_found
test_editing_recomputes_preview_and_has_full_body
test_editing_long_to_short_clears_the_full_body
test_editing_short_to_long_stores_a_full_body
test_editing_a_progress_chapter_changes_the_resolved_position
test_editing_does_not_change_the_positions_copied_onto_replies
```

The ownership check is trivially bypassable — each installation declares its own
`MEMBER_NAME` and could declare anything. It is there to prevent accidents, which
is what it is for, and the docstring should say so rather than implying security.

The last test pins deliberate behaviour: a reply's position is a snapshot of where
the conversation started, and editing the parent does not rewrite history.

## 5.4 `DeletePost`

```
test_owner_can_delete_their_own_post
test_non_owner_returns_not_post_owner
test_deleting_a_post_archives_its_replies
test_replies_are_archived_before_the_parent
test_deleting_a_reply_does_not_touch_its_parent
test_a_failure_partway_through_triggers_compensation
```

Notion does not cascade. Archive the replies explicitly, **before** the parent, so
that a failure partway through leaves the parent visible with some replies missing
rather than a vanished parent with orphans still counting against the query budget.

This is the second operation that justifies the unit of work. Run the whole delete
inside one scope.

## 5.5 `GetFeed`

Returns book, positions, and the assembled post tree. Delegates to
`FeedAssembler`, which is where the tests concentrate.

```
test_top_level_posts_are_newest_first
test_replies_are_nested_under_their_parent
test_replies_are_ordered_oldest_first_within_a_post
test_orphan_replies_whose_parent_is_missing_are_dropped
test_type_filter_applies_to_top_level_posts_only
test_type_filter_keeps_replies_attached_to_surviving_posts
test_positions_include_an_entry_for_every_roster_member
test_positions_are_null_for_a_member_with_no_progress_post
test_spoiler_flags_are_computed_against_the_viewers_position
test_viewer_with_no_position_sees_no_spoilers
test_replies_are_flagged_independently_of_their_parent
test_scale_is_estimated_when_the_book_has_no_total_chapters
test_scale_accounts_for_posts_beyond_a_stated_total_chapters
test_feed_for_a_book_with_no_posts_returns_empty_with_null_positions
```

Three of these encode decisions that a reasonable implementation gets wrong:

- **The type filter runs after nesting, not in the query.** Filtering to
  `Thought` in Notion would strip the replies off the thoughts.
- **Positions include every roster member**, with nulls for anyone who has not
  posted progress. The spine renders "hasn't started" as a state and cannot if the
  member is simply absent from the array.
- **Replies are flagged independently** rather than inheriting the parent's
  computed flag. They will usually agree, since a reply copies the parent's
  position — but revealing a parent must not silently reveal replies the member
  has not chosen to see.

The assembler receives `SpoilerPolicy`, `PositionResolver`, and `ScaleCalculator`
by constructor injection. Its tests pass a stub policy where the assembly logic is
what is under test, and the real policy where the interaction is.

## 5.6 `AddBook`, `UpdateBook`, `ListBooks`

```
test_add_book_requires_a_title
test_add_book_defaults_status_to_upcoming
test_add_book_accepts_a_title_alone
test_setting_a_book_current_pauses_the_previously_current_book
test_setting_a_book_current_when_none_was_current_pauses_nothing
test_updating_an_unrelated_field_does_not_disturb_the_current_book
test_list_books_orders_currently_reading_then_upcoming_then_paused_then_finished
test_list_books_orders_alphabetically_within_a_status_group
```

A title is the only required field. Author and total chapters are optional and
fillable later — the spine calibrates itself without them, and demanding a chapter
count means looking something up before you can use the app.

The demoted book becomes `Paused`, not `Finished`. The app cannot tell whether you
finished a book or set it aside, and guessing writes a false claim into the
owner's Notion.

Status ordering happens in Python — Notion cannot sort by select option order.

## 5.7 `GetPostBody`

```
test_returns_the_preview_when_the_post_has_no_full_body
test_fetches_the_full_body_when_has_full_body_is_true
test_does_not_call_the_repository_when_has_full_body_is_false
test_missing_post_returns_post_not_found
```

The third test is the point of the whole preview/full-body split. Verify it by
asserting on the in-memory repository's call log, not by mocking.

## 5.8 `application/caching.py`

`CachingFeedQuery` implements the same interface as `GetFeed` and wraps an
instance of it. 20-second TTL, keyed by book and filter.

```
test_second_call_within_the_ttl_does_not_reach_the_inner_use_case
test_call_after_the_ttl_reaches_the_inner_use_case
test_different_books_are_cached_separately
test_different_filters_are_cached_separately
test_a_write_invalidates_every_cached_entry
test_the_cache_is_bypassed_for_a_different_viewer
```

The last test matters: spoiler flags are viewer-specific, so the cache key must
include the viewer or the **View as** control will serve the wrong blur state.

Invalidation happens in **one place** — a hook invoked on successful commit, not at
each write site. A stale feed after posting is the first bug the owner will hit and
will report as "the app doesn't work."

Inject the clock. A cache test that sleeps for 20 seconds will be deleted by the
third person who runs the suite.

## Acceptance checks

- [ ] Every use case returns `Result`; the architecture test enforces it
- [ ] `app/application` is at 100% line and branch coverage
- [ ] No test in this phase touches `httpx`, `respx`, or FastAPI
- [ ] No use case imports from `app.adapters` or `app.interface`
- [ ] `pytest tests/unit tests/contract` still under two seconds
- [ ] Every domain error defined in Phase 2 is returned by at least one use case,
      or deleted
