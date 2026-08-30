from datetime import datetime, timedelta, timezone

import pytest

from app.domain.entities import Post
from app.domain.services import (
    MAX_BODY,
    MIN_SCALE,
    BodySplitter,
    PositionResolver,
    ScaleCalculator,
)
from app.domain.values import BookId, MemberName, Position, PostId, PostType

ADA = MemberName("Ada")
GRACE = MemberName("Grace")
T0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def progress(member, chapter, page=None, minutes=0) -> Post:
    return Post(
        id=PostId(f"p{member}{chapter}{minutes}"),
        book_id=BookId("b1"),
        member=member,
        type=PostType.PROGRESS,
        position=Position(chapter, page),
        created_at=T0 + timedelta(minutes=minutes),
        edited_at=T0 + timedelta(minutes=minutes),
    )


def other(member, post_type, chapter=5, minutes=0, **kw) -> Post:
    return Post(
        id=PostId(f"o{member}{minutes}"),
        book_id=BookId("b1"),
        member=member,
        type=post_type,
        body_preview="...",
        position=Position(chapter),
        created_at=T0 + timedelta(minutes=minutes),
        edited_at=T0 + timedelta(minutes=minutes),
        **kw,
    )


class TestPositionResolver:
    resolve = staticmethod(PositionResolver().resolve)

    def test_resolver_returns_position_from_only_progress_post(self):
        assert self.resolve([progress(ADA, 9, 204)]) == {ADA: Position(9, 204)}

    def test_resolver_uses_latest_progress_post_not_highest_chapter(self):
        """A member who mistypes chapter 40 for chapter 4 fixes it by posting
        again. Highest-wins would strand them for the rest of the book."""
        posts = [progress(ADA, 40, minutes=1), progress(ADA, 4, minutes=2)]
        assert self.resolve(posts) == {ADA: Position(4)}

    def test_resolver_ignores_thoughts_and_questions(self):
        posts = [
            progress(ADA, 4, minutes=1),
            other(ADA, PostType.THOUGHT, chapter=90, minutes=2),
            other(ADA, PostType.QUESTION, chapter=91, minutes=3),
        ]
        assert self.resolve(posts) == {ADA: Position(4)}

    def test_resolver_ignores_replies(self):
        posts = [
            progress(ADA, 4, minutes=1),
            other(
                ADA,
                PostType.REPLY,
                chapter=90,
                minutes=2,
                parent_post_id=PostId("parent"),
            ),
        ]
        assert self.resolve(posts) == {ADA: Position(4)}

    def test_resolver_omits_members_with_no_progress_posts(self):
        posts = [progress(ADA, 4), other(GRACE, PostType.THOUGHT)]
        assert self.resolve(posts) == {ADA: Position(4)}

    def test_resolver_handles_two_progress_posts_with_identical_timestamps(self):
        """Notion timestamps have second resolution, so a tie is reachable.
        Last in input order wins, deterministically."""
        first, second = progress(ADA, 7), progress(ADA, 8)
        assert self.resolve([first, second]) == {ADA: Position(8)}
        assert self.resolve([second, first]) == {ADA: Position(7)}

    def test_resolver_is_independent_of_input_order(self):
        """The feed query sorts created_time descending, so the resolver
        normally sees the newest post first and must not take the last one it
        happens to walk past."""
        newest_first = [progress(ADA, 4, minutes=2), progress(ADA, 40, minutes=1)]
        assert self.resolve(newest_first) == {ADA: Position(4)}
        assert self.resolve(list(reversed(newest_first))) == {ADA: Position(4)}

    def test_resolver_tracks_each_member_separately(self):
        posts = [progress(ADA, 4), progress(GRACE, 12, 301)]
        assert self.resolve(posts) == {ADA: Position(4), GRACE: Position(12, 301)}

    def test_resolver_returns_empty_for_no_posts(self):
        assert self.resolve([]) == {}

    def test_resolver_ignores_a_progress_post_that_was_never_saved(self):
        unsaved = Post(
            book_id=BookId("b1"),
            member=ADA,
            type=PostType.PROGRESS,
            position=Position(9),
        )
        assert self.resolve([unsaved]) == {}


class TestBodySplitter:
    split = staticmethod(BodySplitter().split)

    def test_short_body_becomes_preview_with_no_full_body(self):
        assert self.split("A short thought.") == ("A short thought.", False, None)

    def test_body_at_exactly_1900_chars_has_no_full_body(self):
        body = "x" * 1900
        assert self.split(body) == (body, False, None)

    def test_long_body_preview_is_at_most_1900_chars(self):
        preview, has_full, _ = self.split("word " * 1000)
        assert len(preview) <= 1900
        assert has_full

    def test_long_body_preview_cuts_at_a_word_boundary(self):
        preview, _, _ = self.split("word " * 1000)
        assert not preview.endswith("wor")
        assert preview == preview.rstrip()

    def test_long_body_with_no_whitespace_cuts_at_the_hard_limit(self):
        preview, has_full, full = self.split("x" * 5000)
        assert len(preview) == 1900
        assert has_full
        assert full == "x" * 5000

    def test_long_body_full_text_is_returned_complete_including_the_preview_portion(
        self,
    ):
        """The preview and the full body overlap on purpose. Storing only the
        remainder would mean reassembling a body from two sources on every
        edit, which is exactly how posts get corrupted."""
        body = "word " * 1000
        preview, _, full = self.split(body)
        assert full == body
        assert full.startswith(preview)

    def test_body_over_200000_chars_is_rejected(self):
        """A Notion rich text array holds at most 100 objects of 2000 chars."""
        with pytest.raises(ValueError, match="200000|200,000"):
            self.split("x" * (MAX_BODY + 1))

    def test_body_at_exactly_the_ceiling_is_accepted(self):
        preview, has_full, full = self.split("x" * MAX_BODY)
        assert has_full and full is not None and len(full) == MAX_BODY

    def test_empty_body_is_allowed(self):
        """A bare position is a valid Progress post."""
        assert self.split("") == ("", False, None)


class TestScaleCalculator:
    scale = staticmethod(ScaleCalculator().calculate)

    def test_scale_uses_total_chapters_when_known(self):
        assert self.scale(total_chapters=30, observed_max=12) == (30, False)

    def test_scale_is_not_estimated_when_total_chapters_known(self):
        assert self.scale(total_chapters=30, observed_max=12)[1] is False

    def test_scale_infers_from_highest_observed_chapter_with_headroom(self):
        assert self.scale(total_chapters=None, observed_max=50) == (60, True)

    def test_scale_is_estimated_when_total_chapters_unknown(self):
        assert self.scale(total_chapters=None, observed_max=50)[1] is True

    def test_scale_has_a_minimum_of_ten(self):
        assert self.scale(total_chapters=None, observed_max=3) == (MIN_SCALE, True)

    def test_scale_with_no_observations_and_no_total_returns_minimum(self):
        assert self.scale(total_chapters=None, observed_max=None) == (MIN_SCALE, True)

    def test_scale_never_falls_below_the_highest_observed_chapter(self):
        """The trap: chapter 400 in a book whose Total Chapters says 30 must
        still fit on the track rather than drawing a tick off the end."""
        assert self.scale(total_chapters=30, observed_max=400)[0] >= 400

    def test_scale_extends_past_a_stated_total_without_becoming_estimated(self):
        """is_estimated tracks whether the book told us its length, not whether
        the number was adjusted."""
        assert self.scale(total_chapters=30, observed_max=400) == (400, False)

    def test_a_stated_total_below_the_minimum_is_still_the_true_scale(self):
        """The minimum of ten belongs to the inferred branch only. A known total
        gives the true scale, and a 3-chapter novella must not be drawn as a
        10-chapter book."""
        assert self.scale(total_chapters=3, observed_max=None) == (3, False)

    def test_headroom_rounds_up(self):
        assert self.scale(total_chapters=None, observed_max=11) == (14, True)
