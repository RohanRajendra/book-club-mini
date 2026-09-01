from datetime import datetime, timedelta, timezone

import pytest

from app.domain.entities import Post
from app.domain.services import (
    MAX_BODY,
    MIN_PREVIEW,
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

    def test_a_tie_resolves_to_the_post_listed_first(self):
        """Notion truncates `created_time` to the *minute* — verified against a
        live workspace, where every page reports `:00.000Z`. So a correction
        posted seconds after a mistake ties with it, and this is the ordinary
        case rather than an exotic one.

        `list_for_book` is newest-first, ties included, so the first of a tied
        pair is the correction. Keeping the last one kept the mistake — the
        precise workflow the resolver was written to protect."""
        posts = [progress(ADA, 4, minutes=0), progress(ADA, 40, minutes=0)]
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
        """First in input order wins, deterministically.

        This test previously asserted the opposite, on the reasoning that a tie
        is arbitrary so any deterministic answer would do. It is not arbitrary:
        input arrives newest-first, so taking the last one takes the oldest —
        and the test below already says the resolver "must not take the last
        one it happens to walk past". It only ever checked that with distinct
        timestamps, where the rule makes no difference."""
        first, second = progress(ADA, 7), progress(ADA, 8)
        assert self.resolve([first, second]) == {ADA: Position(7)}
        assert self.resolve([second, first]) == {ADA: Position(8)}

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

    def test_space_sparse_body_is_not_cut_back_to_its_one_early_space(self):
        """The reported shape: a one-word lead-in and then an unbroken run.

        Honouring the only word boundary would preview a 5000-character post as
        the single character `I`."""
        preview, _, _ = self.split("I " + "x" * 5000)
        assert len(preview) >= 1520

    def test_a_newline_counts_as_a_word_boundary(self):
        """Prose that breaks by line rather than by space still cuts cleanly."""
        preview, _, _ = self.split("word\n" * 1000)
        assert not preview.endswith("wor")
        assert preview == preview.rstrip()

    def test_a_boundary_that_keeps_most_of_the_budget_is_honoured(self):
        """A long token at the end is dropped, not sliced, while it is cheap to
        do so."""
        body = "word " * 340 + "u" * 200 + " tail"
        preview, _, _ = self.split(body)
        assert preview.endswith("word")
        assert len(preview) >= 1520

    def test_a_run_of_whitespace_at_the_cut_is_not_left_dangling(self):
        """The boundary match lands on the last whitespace of a run, so the
        rest of the run is still on the end of the preview until it is
        stripped."""
        preview, _, _ = self.split("word  " * 400)
        assert preview.endswith("word")
        assert preview == preview.rstrip()

    def test_a_boundary_at_exactly_the_floor_is_honoured(self):
        """The threshold is inclusive: a preview of exactly MIN_PREVIEW is
        long enough."""
        preview, _, _ = self.split("w" * MIN_PREVIEW + " " + "x" * 1000)
        assert preview == "w" * MIN_PREVIEW

    def test_a_boundary_one_character_below_the_floor_is_ignored(self):
        preview, _, _ = self.split("w" * (MIN_PREVIEW - 1) + " " + "x" * 1000)
        assert len(preview) == 1900

    def test_a_boundary_that_would_discard_most_of_the_budget_is_ignored(self):
        """One space at 100 characters in, then an unbroken run: cutting there
        would throw away 95% of the preview, so the limit wins."""
        preview, _, _ = self.split("w" * 100 + " " + "x" * 5000)
        assert len(preview) == 1900

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
        still fit on the track rather than drawing a tick off the end.

        The write paths now refuse to create that post, so this defends against
        a row edited directly in Notion — a route the docs tell members they
        may use. Rendering is where an overshoot has to be survivable."""
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


class TestScaleCalculatorForAFinishedBook:
    """A finished book with no stated length has already ended.

    Headroom exists to leave room for chapters not yet reached. There are none,
    so it draws the furthest tick at 83% of the track and tells a member who
    has finished the book that there is more of it left.
    """

    scale = staticmethod(ScaleCalculator().calculate)

    def test_the_furthest_posted_chapter_becomes_the_length(self):
        assert self.scale(
            total_chapters=None, observed_max=45, is_finished=True
        ) == (45, False)

    def test_it_is_not_reported_as_an_estimate(self):
        """The track is drawn solid and labelled with the chapter rather than
        `?`, because the far end is no longer a guess about a book still being
        read."""
        assert self.scale(
            total_chapters=None, observed_max=45, is_finished=True
        )[1] is False

    def test_a_stated_total_still_wins(self):
        """Evidence from posts is the fallback, not an override."""
        assert self.scale(
            total_chapters=50, observed_max=45, is_finished=True
        ) == (50, False)

    def test_the_minimum_does_not_apply(self):
        """The floor of ten belongs to the guessing branch. A finished novella
        of three chapters must not be drawn as a ten-chapter book."""
        assert self.scale(
            total_chapters=None, observed_max=3, is_finished=True
        ) == (3, False)

    def test_no_posted_chapters_falls_back_to_a_guess(self):
        """Marked finished with nothing to infer from. There is no evidence to
        prefer, so this stays an estimate rather than becoming a scale of
        zero."""
        assert self.scale(
            total_chapters=None, observed_max=None, is_finished=True
        ) == (MIN_SCALE, True)

    def test_an_unfinished_book_still_gets_headroom(self):
        assert self.scale(
            total_chapters=None, observed_max=45, is_finished=False
        ) == (54, True)
