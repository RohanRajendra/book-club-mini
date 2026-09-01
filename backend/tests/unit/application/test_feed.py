"""FeedAssembler — where the GetFeed tests concentrate."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from app.application.dto import Spine
from app.application.feed import FeedAssembler
from app.domain.entities import Post
from app.domain.policies import ChapterFirstSpoilerPolicy, SpoilerPolicy
from app.domain.services import PositionResolver, ScaleCalculator
from app.domain.values import (
    BookId,
    BookStatus,
    MemberName,
    Position,
    PostId,
    PostType,
)
from tests.builders import ADA, GRACE, ROSTER, at_minute, make_book, make_post, make_reply


class NeverSpoiler(SpoilerPolicy):
    """A stub for the tests where assembly, not the rule, is under test."""

    def is_spoiler(self, post, viewer, viewer_position) -> bool:
        return False


def assembler(policy: SpoilerPolicy | None = None) -> FeedAssembler:
    return FeedAssembler(
        spoiler_policy=policy or ChapterFirstSpoilerPolicy(),
        position_resolver=PositionResolver(),
        scale_calculator=ScaleCalculator(),
        roster=ROSTER,
    )


def post(pid: str, *, minute: int, **overrides) -> Post:
    return make_post(id=PostId(pid), created_at=at_minute(minute), **overrides)


def progress(pid: str, member: MemberName, chapter: int, minute: int) -> Post:
    return make_post(
        id=PostId(pid),
        member=member,
        type=PostType.PROGRESS,
        position=Position(chapter),
        body_preview="",
        created_at=at_minute(minute),
    )


class TestOrderingAndNesting:
    def test_top_level_posts_are_newest_first(self):
        posts = [post("a", minute=1), post("b", minute=5), post("c", minute=3)]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert [fp.post.id.value for fp in feed.posts] == ["b", "c", "a"]

    def test_replies_are_nested_under_their_parent(self):
        parent = post("parent", minute=1)
        reply = make_reply(parent, GRACE, id=PostId("reply"), created_at=at_minute(2))
        feed = assembler().assemble(make_book(), [parent, reply], ADA)
        assert len(feed.posts) == 1
        assert [fp.post.id.value for fp in feed.posts[0].replies] == ["reply"]

    def test_replies_are_ordered_oldest_first_within_a_post(self):
        """A conversation reads downward inside a feed that reads upward."""
        parent = post("parent", minute=1)
        replies = [
            make_reply(parent, GRACE, id=PostId("r2"), created_at=at_minute(9)),
            make_reply(parent, ADA, id=PostId("r1"), created_at=at_minute(4)),
        ]
        feed = assembler().assemble(make_book(), [parent, *replies], ADA)
        assert [fp.post.id.value for fp in feed.posts[0].replies] == ["r1", "r2"]

    def test_orphan_replies_whose_parent_is_missing_are_dropped(self):
        orphan = make_post(
            id=PostId("orphan"),
            type=PostType.REPLY,
            parent_post_id=PostId("gone"),
            created_at=at_minute(2),
        )
        feed = assembler().assemble(make_book(), [orphan], ADA)
        assert feed.posts == []


class TestFiltering:
    def make_posts(self) -> list[Post]:
        thought = post("thought", minute=1, type=PostType.THOUGHT)
        question = post("question", minute=2, type=PostType.QUESTION)
        prog = progress("prog", ADA, 4, minute=3)
        reply = make_reply(thought, GRACE, id=PostId("reply"), created_at=at_minute(4))
        return [thought, question, prog, reply]

    def test_type_filter_applies_to_top_level_posts_only(self):
        feed = assembler().assemble(
            make_book(), self.make_posts(), ADA, PostType.THOUGHT
        )
        assert [fp.post.id.value for fp in feed.posts] == ["thought"]

    def test_type_filter_keeps_replies_attached_to_surviving_posts(self):
        """Filtering to Thought in Notion would strip the replies off the
        thoughts. The filter runs after nesting."""
        feed = assembler().assemble(
            make_book(), self.make_posts(), ADA, PostType.THOUGHT
        )
        assert [fp.post.id.value for fp in feed.posts[0].replies] == ["reply"]

    def test_counts_cover_every_chip_regardless_of_the_active_filter(self):
        """The client filters locally, so it needs all four counts at once
."""
        feed = assembler().assemble(
            make_book(), self.make_posts(), ADA, PostType.QUESTION
        )
        assert feed.counts == {
            "all": 3,
            "progress": 1,
            "thought": 1,
            "question": 1,
        }

    def test_counts_exclude_replies(self):
        feed = assembler().assemble(make_book(), self.make_posts(), ADA)
        assert feed.counts["all"] == 3


class TestPositions:
    def test_positions_include_an_entry_for_every_roster_member(self):
        feed = assembler().assemble(make_book(), [progress("p", ADA, 9, 1)], ADA)
        assert set(feed.positions) == set(ROSTER)

    def test_positions_are_null_for_a_member_with_no_progress_post(self):
        feed = assembler().assemble(make_book(), [progress("p", ADA, 9, 1)], ADA)
        assert feed.positions[GRACE] is None

    def test_feed_for_a_book_with_no_posts_returns_empty_with_null_positions(self):
        feed = assembler().assemble(make_book(), [], ADA)
        assert feed.posts == []
        assert feed.positions == {ADA: None, GRACE: None}


class TestSpoilerFlags:
    def test_spoiler_flags_are_computed_against_the_viewers_position(self):
        posts = [
            progress("ada", ADA, 4, minute=1),
            post("ahead", minute=2, member=GRACE, position=Position(9)),
            post("behind", minute=3, member=GRACE, position=Position(2)),
        ]
        feed = assembler().assemble(make_book(), posts, ADA)
        flags = {fp.post.id.value: fp.is_spoiler for fp in feed.posts}
        assert flags == {"ada": False, "ahead": True, "behind": False}

    def test_viewer_with_no_position_sees_no_spoilers(self):
        posts = [post("ahead", minute=2, member=GRACE, position=Position(400))]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert feed.posts[0].is_spoiler is False

    def test_replies_are_flagged_independently_of_their_parent(self):
        """Revealing a parent must not silently reveal replies the member has
        not chosen to see."""
        posts = [
            progress("ada", ADA, 4, minute=1),
            post("parent", minute=2, member=GRACE, position=Position(2)),
        ]
        # Not make_reply: this reply deliberately carries a position its
        # parent does not, which is the whole point of the test.
        reply = make_post(
            id=PostId("reply"),
            member=GRACE,
            type=PostType.REPLY,
            parent_post_id=PostId("parent"),
            position=Position(90),
            created_at=at_minute(3),
        )
        feed = assembler().assemble(make_book(), [*posts, reply], ADA)
        parent = next(fp for fp in feed.posts if fp.post.id.value == "parent")
        assert parent.is_spoiler is False
        assert parent.replies[0].is_spoiler is True

    def test_is_own_marks_the_viewers_posts(self):
        posts = [post("mine", minute=1, member=ADA), post("hers", minute=2, member=GRACE)]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert {fp.post.id.value: fp.is_own for fp in feed.posts} == {
            "mine": True,
            "hers": False,
        }

    def test_a_stub_policy_isolates_assembly_from_the_rule(self):
        posts = [progress("ada", ADA, 4, minute=1), post("ahead", minute=2, member=GRACE, position=Position(400))]
        feed = assembler(NeverSpoiler()).assemble(make_book(), posts, ADA)
        assert all(not fp.is_spoiler for fp in feed.posts)


def test_your_own_posts_are_not_blurred_when_notion_spells_your_name_differently():
    """The harm behind case-sensitive member names.

    A post the viewer wrote is never a spoiler for them. With `Ada` in the
    roster and `ada` in Notion the comparison said two different people, so a
    member's own posts came back blurred and their position was attributed to
    nobody."""
    posts = [
        progress("p", MemberName("ada"), 40, 1),
        post("t", minute=2, member=MemberName("ada"), position=Position(40)),
    ]
    feed = assembler(ChapterFirstSpoilerPolicy()).assemble(
        make_book(total_chapters=None), posts, ADA
    )
    assert feed.positions[ADA] == Position(40)
    assert [entry.is_spoiler for entry in feed.posts] == [False, False]
    assert all(entry.is_own for entry in feed.posts)


class TestOddTimestampsDoNotTakeTheFeedDown:
    """Sorting is the one place where a single bad row breaks everything.

    `sorted` raises on the first incomparable pair, so one post with no
    timestamp, or one naive datetime among aware ones, is not a post that
    renders oddly — it is a 500 for the whole book.
    """

    def test_a_post_with_no_created_at_does_not_crash_the_feed(self):
        posts = [post("a", minute=1), post("b", minute=2)]
        posts[0] = replace(posts[0], created_at=None)
        feed = assembler().assemble(make_book(), posts, ADA)
        assert len(feed.posts) == 2

    def test_a_post_with_no_created_at_sorts_oldest(self):
        """Newest-first, and an untimestamped post is not news."""
        posts = [replace(post("a", minute=1), created_at=None), post("b", minute=2)]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert [entry.post.id.value for entry in feed.posts] == ["b", "a"]

    def test_a_naive_datetime_does_not_crash_the_feed(self):
        """Aware and naive datetimes cannot be compared at all. Notion always
        sends an offset, so this is a hand-edited row or a future adapter —
        neither of which should be able to take the feed down."""
        naive = datetime(2026, 3, 1, 12, 30)
        posts = [replace(post("a", minute=1), created_at=naive), post("b", minute=2)]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert len(feed.posts) == 2

    def test_a_naive_datetime_is_read_as_utc_when_ordering(self):
        posts = [
            replace(post("a", minute=1), created_at=datetime(2026, 3, 1, 12, 30)),
            post("b", minute=2),
        ]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert [entry.post.id.value for entry in feed.posts] == ["a", "b"]

    def test_a_reply_with_no_created_at_does_not_crash_the_thread(self):
        parent = post("p", minute=1)
        replies = [
            replace(make_reply(parent, GRACE, id=PostId("r1")), created_at=None),
            make_reply(parent, GRACE, id=PostId("r2"), created_at=at_minute(3)),
        ]
        feed = assembler().assemble(make_book(), [parent, *replies], ADA)
        assert [r.post.id.value for r in feed.posts[0].replies] == ["r1", "r2"]

    def test_positions_survive_a_naive_timestamp(self):
        """PositionResolver compares timestamps too, and one bad row there
        loses every member's position rather than one post."""
        posts = [
            replace(progress("a", ADA, 4, 1), created_at=datetime(2026, 3, 1, 12, 0)),
            progress("b", ADA, 9, 2),
        ]
        feed = assembler().assemble(make_book(), posts, ADA)
        assert feed.positions[ADA] == Position(9)


class TestScale:
    def test_scale_is_estimated_when_the_book_has_no_total_chapters(self):
        book = make_book(total_chapters=None)
        feed = assembler().assemble(book, [progress("p", ADA, 5, 1)], ADA)
        assert feed.spine.is_estimated is True
        assert feed.spine.max_chapter == 10

    def test_scale_accounts_for_posts_beyond_a_stated_total_chapters(self):
        book = make_book(total_chapters=30)
        feed = assembler().assemble(book, [progress("p", ADA, 400, 1)], ADA)
        assert feed.spine.max_chapter == 400
        assert feed.spine.is_estimated is False

    def test_scale_uses_a_stated_total_when_no_post_exceeds_it(self):
        feed = assembler().assemble(make_book(total_chapters=30), [], ADA)
        assert feed.spine == Spine(max_chapter=30, is_estimated=False)

    def test_scale_observes_replies_and_thoughts_not_only_progress(self):
        book = make_book(total_chapters=None)
        feed = assembler().assemble(book, [post("t", minute=1, position=Position(50))], ADA)
        assert feed.spine.max_chapter == 60


class TestScaleForAFinishedBook:
    """A finished book with no stated length ends at its furthest chapter.

    Headroom leaves room for chapters not yet reached, and a finished book has
    none — so it drew the last tick at 83% of the track and told a member who
    had finished the book there was more of it.
    """

    def test_the_track_ends_at_the_furthest_posted_chapter(self):
        book = make_book(total_chapters=None, status=BookStatus.FINISHED)
        feed = assembler().assemble(book, [progress("p", ADA, 45, 1)], ADA)
        assert feed.spine == Spine(max_chapter=45, is_estimated=False)

    def test_a_thought_counts_as_evidence_not_only_progress(self):
        """Writing about chapter 45 means someone reached chapter 45."""
        book = make_book(total_chapters=None, status=BookStatus.FINISHED)
        feed = assembler().assemble(
            book, [post("t", minute=1, position=Position(45))], ADA
        )
        assert feed.spine.max_chapter == 45

    def test_a_stated_total_still_wins(self):
        book = make_book(total_chapters=50, status=BookStatus.FINISHED)
        feed = assembler().assemble(book, [progress("p", ADA, 45, 1)], ADA)
        assert feed.spine == Spine(max_chapter=50, is_estimated=False)

    def test_a_finished_book_with_nothing_posted_is_still_a_guess(self):
        book = make_book(total_chapters=None, status=BookStatus.FINISHED)
        feed = assembler().assemble(book, [], ADA)
        assert feed.spine == Spine(max_chapter=10, is_estimated=True)

    def test_a_book_still_being_read_keeps_its_headroom(self):
        for status in (BookStatus.CURRENTLY_READING, BookStatus.PAUSED, BookStatus.UPCOMING):
            book = make_book(total_chapters=None, status=status)
            feed = assembler().assemble(book, [progress("p", ADA, 45, 1)], ADA)
            assert feed.spine == Spine(max_chapter=54, is_estimated=True), status
