from datetime import datetime, timedelta, timezone

import pytest

from app.domain.entities import Book, Post
from app.domain.values import BookId, BookStatus, MemberName, Position, PostId, PostType

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def a_post(**overrides) -> Post:
    return Post(
        **{
            "id": PostId("p1"),
            "book_id": BookId("b1"),
            "member": MemberName("Ada"),
            "type": PostType.THOUGHT,
            "body_preview": "A thought.",
            "has_full_body": False,
            "position": Position(9, 204),
            "parent_post_id": None,
            "created_at": NOW,
            "edited_at": NOW,
            **overrides,
        }
    )


class TestBook:
    def test_book_rejects_blank_title(self):
        for title in ("", "   "):
            with pytest.raises(ValueError, match="title"):
                Book(id=BookId("b1"), title=title)

    def test_book_defaults_status_to_upcoming(self):
        assert Book(id=BookId("b1"), title="Piranesi").status is BookStatus.UPCOMING

    def test_book_rejects_zero_or_negative_total_chapters(self):
        for total in (0, -4):
            with pytest.raises(ValueError, match="total_chapters"):
                Book(id=BookId("b1"), title="Piranesi", total_chapters=total)

    def test_book_allows_missing_author_and_total_chapters(self):
        book = Book(id=BookId("b1"), title="Piranesi")
        assert book.author is None
        assert book.total_chapters is None

    def test_an_unsaved_book_has_no_id(self):
        """A book being created has no Notion page yet (spec-deltas D9)."""
        assert Book(title="Piranesi").id is None


class TestPost:
    def test_post_is_reply_when_parent_post_id_present(self):
        assert a_post(parent_post_id=PostId("parent"), type=PostType.REPLY).is_reply
        assert not a_post().is_reply

    def test_post_type_is_reply_whenever_parent_post_id_present(self):
        """The entity refuses to hold a contradiction: a post with a parent that
        claims to be a Thought would blur and render as a top-level post."""
        with pytest.raises(ValueError, match="Reply"):
            a_post(parent_post_id=PostId("parent"), type=PostType.THOUGHT)

    def test_progress_post_requires_a_position(self):
        with pytest.raises(ValueError, match="position"):
            a_post(type=PostType.PROGRESS, position=None)

    def test_thought_and_question_allow_no_position(self):
        for post_type in (PostType.THOUGHT, PostType.QUESTION):
            assert a_post(type=post_type, position=None).position is None

    def test_an_unsaved_post_has_no_id(self):
        assert a_post(id=None, created_at=None, edited_at=None).id is None

    def test_post_was_edited_is_false_when_timestamps_match(self):
        assert not a_post(created_at=NOW, edited_at=NOW).was_edited

    def test_post_was_edited_is_false_for_a_create_then_block_append(self):
        """Creating a long post is a page write followed by a block append, and
        the append bumps last_edited_time. Without a threshold every post over
        1900 characters is born showing `edited` (spec-deltas D10)."""
        post = a_post(created_at=NOW, edited_at=NOW + timedelta(milliseconds=800))
        assert not post.was_edited

    def test_post_was_edited_is_true_after_a_real_edit(self):
        post = a_post(created_at=NOW, edited_at=NOW + timedelta(minutes=5))
        assert post.was_edited

    def test_post_was_edited_is_false_when_never_saved(self):
        assert not a_post(created_at=None, edited_at=None).was_edited

    def test_post_rejects_a_preview_over_the_notion_property_cap(self):
        with pytest.raises(ValueError, match="1900"):
            a_post(body_preview="x" * 1901)

    def test_post_allows_a_preview_at_exactly_the_cap(self):
        assert len(a_post(body_preview="x" * 1900).body_preview) == 1900
