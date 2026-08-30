# Phase 2 — Domain core

**Goal:** every business rule in the app, as pure code with no I/O, at 100%
branch coverage.

**Depends on:** Phase 1. **Touches no network, no framework, no FastAPI.**

This phase produces nothing a user can see. It is the part that must be right
before anything touches Notion, and the part a database swap would preserve
unchanged.

## 2.1 `domain/result.py`

Tests first:

```
test_ok_is_ok_and_unwraps_to_value
test_err_is_not_ok_and_unwraps_to_error
test_unwrap_on_err_raises
test_unwrap_err_on_ok_raises
test_map_transforms_ok_and_passes_err_through
```

Frozen generic dataclasses `Ok[T]` and `Err[E]`, with `Result = Ok[T] | Err[E]`.
Keep the surface at `is_ok`, `unwrap`, `unwrap_err`, `map`. Do not add `and_then`,
`or_else`, or the rest of the combinator family until something needs them.

## 2.2 `domain/errors.py`

A `DomainError` base with a `code: str` class attribute, then one subclass per
expected failure:

`BookNotFound`, `PostNotFound`, `NotPostOwner`, `CannotReplyToReply`,
`ReplyBookMismatch`, `ChapterRequiredForProgress`, `PageRequiresChapter`,
`BodyRequired`, `BodyTooLong`, `TitleRequired`, `UnknownMember`.

```
test_every_domain_error_has_a_unique_code
```

Codes are what the HTTP layer maps on in Phase 6, and duplicates would silently
collapse two failures into one response.

## 2.3 `domain/values.py`

**`PostType`** — enum: `PROGRESS`, `THOUGHT`, `QUESTION`, `REPLY`.

**`Position`** — frozen dataclass, `chapter: int`, `page: int | None`.

```
test_position_rejects_zero_or_negative_chapter
test_position_rejects_zero_or_negative_page
test_position_allows_missing_page
test_position_is_ahead_of_compares_chapter_first
test_position_is_ahead_of_compares_page_within_same_chapter
test_position_is_not_ahead_when_either_page_missing_in_same_chapter
test_position_equal_chapter_and_page_is_not_ahead
```

`is_ahead_of(other) -> bool` holds the ordering. Deliberately **not** total
ordering via `__lt__`: two positions in the same chapter with one page missing are
genuinely incomparable, and `__lt__` would force a false answer. A named method
that returns `False` for "cannot tell" is honest; a comparison operator is not.

**`MemberName`, `BookId`, `PostId`** — thin `NewType`-style wrappers. They cost
nothing and stop the argument-order bug where a book ID lands in a post ID
parameter.

## 2.4 `domain/entities.py`

**`Book`** — `id`, `title`, `author`, `status`, `total_chapters`.

```
test_book_rejects_blank_title
test_book_defaults_status_to_upcoming
test_book_rejects_zero_or_negative_total_chapters
test_book_allows_missing_author_and_total_chapters
```

**`Post`** — `id`, `book_id`, `member`, `type`, `body_preview`, `has_full_body`,
`position`, `parent_post_id`, `created_at`, `edited_at`.

```
test_post_is_reply_when_parent_post_id_present
test_post_type_is_reply_whenever_parent_post_id_present
test_progress_post_requires_a_position
test_thought_and_question_allow_no_position
test_post_was_edited_is_false_when_timestamps_match
```

The entity enforces the invariants that must hold everywhere. Rules that depend on
*other* objects — that a reply's parent is not itself a reply, that a parent shares
the reply's book — belong to use cases in Phase 5, not here. The entity cannot see
the parent.

## 2.5 `domain/policies.py` — the spoiler rule

Write every one of these before writing the policy. This list is the
specification, and each line is a decision from `01-ux-spec.md`:

```
test_own_post_is_never_a_spoiler
test_own_post_far_ahead_is_still_not_a_spoiler
test_nothing_is_a_spoiler_when_viewer_position_unknown
test_post_without_chapter_is_never_a_spoiler
test_later_chapter_is_a_spoiler
test_earlier_chapter_is_not_a_spoiler
test_same_chapter_later_page_is_a_spoiler
test_same_chapter_earlier_page_is_not_a_spoiler
test_same_chapter_is_not_a_spoiler_when_post_page_missing
test_same_chapter_is_not_a_spoiler_when_viewer_page_missing
test_reply_is_evaluated_on_its_own_copied_position
```

`SpoilerPolicy` is an ABC with one method; `ChapterFirstSpoilerPolicy` is the only
implementation. It is a Strategy because the blur rule is the most likely thing in
this app to change, and isolating it means a percent-based variant is a new class
rather than an `if`.

Delegate the comparison to `Position.is_ahead_of` rather than reimplementing it.
Two copies of the ordering rule is how they drift.

## 2.6 `domain/services.py`

**`PositionResolver`** — given a book's posts, return `{member: Position}`.

```
test_resolver_returns_position_from_only_progress_post
test_resolver_uses_latest_progress_post_not_highest_chapter
test_resolver_ignores_thoughts_and_questions
test_resolver_ignores_replies
test_resolver_omits_members_with_no_progress_posts
test_resolver_handles_two_progress_posts_with_identical_timestamps
```

Latest, not highest, so a member who mistypes chapter 40 for chapter 4 can fix it
by posting again. Highest-wins would strand them for the rest of the book. On a
timestamp tie, take the last in the input order and document it — Notion's
timestamps have second resolution and a tie is reachable.

**`BodySplitter`** — given text, return `(preview, has_full_body, full_body|None)`.

```
test_short_body_becomes_preview_with_no_full_body
test_body_at_exactly_1900_chars_has_no_full_body
test_long_body_preview_is_at_most_1900_chars
test_long_body_preview_cuts_at_a_word_boundary
test_long_body_with_no_whitespace_cuts_at_the_hard_limit
test_long_body_full_text_is_returned_complete_including_the_preview_portion
test_body_over_200000_chars_is_rejected
```

The preview and the full body **overlap** — the first 1900 characters exist in both
places. That redundancy is intentional. Storing only the remainder in the block
would mean reassembling a body from two sources across every edit, which is exactly
how posts get corrupted.

200,000 is the ceiling because a Notion rich text array holds at most 100 objects
of 2000 characters.

**`ScaleCalculator`** — the spine.

```
test_scale_uses_total_chapters_when_known
test_scale_is_not_estimated_when_total_chapters_known
test_scale_infers_from_highest_observed_chapter_with_headroom
test_scale_is_estimated_when_total_chapters_unknown
test_scale_has_a_minimum_of_ten
test_scale_with_no_observations_and_no_total_returns_minimum
test_scale_never_falls_below_the_highest_observed_chapter
```

Returns `(max_chapter, is_estimated)`. Inferred scale is
`max(observed) * 1.2`, rounded up, floored at 10. The last test is the trap: if
someone posts chapter 400 of a book whose `Total Chapters` says 30, the scale must
still contain the post rather than drawing a tick off the end of the track.

## 2.7 Coverage gate

Add to `pyproject.toml` a pytest invocation scoped to this package requiring
`--cov-fail-under=100` on `app/domain`, lines and branches.

If a branch is unreachable, delete the branch. Do not write a test that reaches it
artificially, and do not add a `# pragma: no cover` without a comment saying why.

## Acceptance checks

- [ ] `pytest tests/unit` is green and runs in under two seconds
- [ ] `app/domain` is at 100% line and branch coverage
- [ ] No file in `app/domain` imports `httpx`, `fastapi`, `pydantic`, or anything
      from `app.adapters`, `app.application`, or `app.interface`
- [ ] The architecture tests from Phase 1 still pass
- [ ] Reading the test names in `tests/unit/domain/` describes the business rules
      without opening the implementation
