"""The mappers' forgiving behaviour, and the properties they generate.

Scope note: these test *logic*, not payload shape. The property dicts here are
minimal inputs chosen to drive a branch — they are not a claim about what Notion
returns. The claim about payload shape lives in
`tests/integration/test_mappers.py`, which runs against real recorded responses
and skips until they are captured.

The distinction matters because the trap these fixtures guard against is a suite
that goes green against an API that would reject it. A fallback branch cannot
have that problem: it fires precisely when the payload is *not* what Notion
normally sends, because someone hand-edited the row.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.notion.mappers import BookMapper, PostMapper
from app.domain.entities import Book, Post
from app.domain.values import BookId, BookStatus, MemberName, Position, PostId, PostType

BOOKS = BookMapper()
POSTS = PostMapper()


def book_page(**properties) -> dict:
    return {"id": "book-1", "properties": properties}


def post_page(**properties) -> dict:
    return {
        "id": "post-1",
        "created_time": "2026-03-01T12:00:00.000Z",
        "last_edited_time": "2026-03-01T12:00:00.000Z",
        "properties": {
            "Book": {"relation": [{"id": "book-1"}]},
            "Member": {"select": {"name": "Ada"}},
            "Type": {"select": {"name": "Thought"}},
            **properties,
        },
    }


class TestBookFallbacks:
    def test_unknown_status_maps_to_upcoming(self):
        page = book_page(Status={"select": {"name": "Abandoned"}})
        assert BOOKS.to_domain(page).status is BookStatus.UPCOMING

    def test_a_cleared_status_maps_to_upcoming(self):
        assert BOOKS.to_domain(book_page()).status is BookStatus.UPCOMING

    def test_a_known_status_is_preserved(self):
        page = book_page(Status={"select": {"name": "Paused"}})
        assert BOOKS.to_domain(page).status is BookStatus.PAUSED

    def test_a_cleared_title_becomes_untitled_rather_than_raising(self):
        """The entity rejects a blank title, and an untitled row in Notion must
        not 500 the whole feed."""
        assert BOOKS.to_domain(book_page()).title == "Untitled"

    def test_a_zero_total_chapters_maps_to_none(self):
        page = book_page(**{"Total Chapters": {"number": 0}})
        assert BOOKS.to_domain(page).total_chapters is None

    # A Notion update merges, so an omitted property keeps its old value. Every
    # property is therefore always written, with the shape that means "empty":
    # `None` for a number, `[]` for rich text.
    def test_to_properties_writes_every_property_even_when_empty(self):
        properties = BOOKS.to_properties(Book(title="Piranesi"))
        assert set(properties) == {"Title", "Status", "Author", "Total Chapters"}

    def test_an_absent_author_is_written_as_empty_rich_text(self):
        properties = BOOKS.to_properties(Book(title="Piranesi", author=None))
        assert properties["Author"] == {"rich_text": []}

    def test_an_absent_total_chapter_count_is_written_as_a_null_number(self):
        properties = BOOKS.to_properties(Book(title="Piranesi", total_chapters=None))
        assert properties["Total Chapters"] == {"number": None}

    def test_to_properties_includes_author_and_chapters_when_present(self):
        properties = BOOKS.to_properties(
            Book(title="Piranesi", author="Susanna Clarke", total_chapters=30)
        )
        assert properties["Total Chapters"] == {"number": 30}
        assert properties["Author"]["rich_text"][0]["text"]["content"] == "Susanna Clarke"


class TestHandEditedBookText:
    """Notion's text fields are free-form and the docs invite hand-edits.

    A whitespace title reached `Book.__post_init__`, which raises — a `500` on
    `GET /api/books` and on every feed for that book, from typing a space.
    """

    def test_a_whitespace_title_falls_back_instead_of_raising(self):
        page = book_page(Title={"title": [{"plain_text": "   "}]})
        assert BOOKS.to_domain(page).title == "Untitled"

    def test_a_title_is_stripped(self):
        page = book_page(Title={"title": [{"plain_text": "  Piranesi  "}]})
        assert BOOKS.to_domain(page).title == "Piranesi"

    def test_a_whitespace_author_reads_as_no_author(self):
        """Blank-but-present is not a state a book should have: it renders as
        an empty author line that looks like a bug."""
        page = book_page(Author={"rich_text": [{"plain_text": "   "}]})
        assert BOOKS.to_domain(page).author is None

    def test_an_author_is_stripped(self):
        page = book_page(Author={"rich_text": [{"plain_text": " Susanna Clarke "}]})
        assert BOOKS.to_domain(page).author == "Susanna Clarke"


class TestPostFallbacks:
    def test_an_unknown_type_falls_back_to_thought(self):
        assert POSTS.to_domain(post_page(Type={"select": {"name": "Musing"}})).type is (
            PostType.THOUGHT
        )

    def test_a_parent_id_forces_type_reply(self):
        """A hand-edit can leave a reply typed as a Thought; the parent is what
        makes it a reply, and the entity refuses the contradiction."""
        page = post_page(
            Type={"select": {"name": "Thought"}},
            **{"Parent Post ID": {"rich_text": [{"plain_text": "parent-1"}]}},
        )
        post = POSTS.to_domain(page)
        assert post.type is PostType.REPLY
        assert post.parent_post_id == PostId("parent-1")

    def test_a_whitespace_only_parent_id_maps_to_none(self):
        page = post_page(**{"Parent Post ID": {"rich_text": [{"plain_text": "   "}]}})
        assert POSTS.to_domain(page).parent_post_id is None

    def test_a_progress_row_with_no_chapter_becomes_a_thought(self):
        """The entity requires a position on Progress. A hand-edit clearing the
        chapter must degrade, not 500."""
        page = post_page(Type={"select": {"name": "Progress"}})
        assert POSTS.to_domain(page).type is PostType.THOUGHT

    def test_a_page_without_a_chapter_is_dropped(self):
        page = post_page(Chapter={"number": None}, Page={"number": 204})
        assert POSTS.to_domain(page).position is None

    def test_a_zero_page_maps_to_no_page(self):
        page = post_page(Chapter={"number": 9}, Page={"number": 0})
        assert POSTS.to_domain(page).position == Position(9)

    def test_a_cleared_member_maps_to_unknown(self):
        page = post_page(Member={"select": None})
        assert POSTS.to_domain(page).member == MemberName("Unknown")

    def test_missing_timestamps_map_to_none(self):
        page = post_page()
        page.pop("created_time")
        page["last_edited_time"] = None
        post = POSTS.to_domain(page)
        assert post.created_at is None and post.edited_at is None


class TestAPostWithNoBookIsNotInvented:
    """A post whose Book relation is empty cannot be represented.

    It used to be given the fabricated id `BookId("orphan")` — a value that
    belongs to no book, breaks the guarantee that an identifier never silently
    stands in for another, and leaves the row invisible either way, since the
    feed queries by relation and this one has none.
    """

    def test_a_post_with_no_book_relation_maps_to_nothing(self):
        page = post_page()
        page["properties"]["Book"] = {"relation": []}
        assert POSTS.to_domain(page) is None

    def test_a_post_with_a_missing_book_property_maps_to_nothing(self):
        page = post_page()
        del page["properties"]["Book"]
        assert POSTS.to_domain(page) is None

    def test_a_post_with_a_book_still_maps(self):
        assert POSTS.to_domain(post_page()).book_id == BookId("book-1")

    def test_the_fabricated_orphan_id_is_gone(self):
        """Named because it was a real value in a real database, and anything
        still reading it would now be reading a book that never existed."""
        page = post_page()
        page["properties"]["Book"] = {"relation": []}
        assert POSTS.to_domain(page) != Post(
            book_id=BookId("orphan"),
            member=MemberName("Ada"),
            type=PostType.THOUGHT,
        )


class TestTimestampFallbacks:
    """One bad timestamp is a 500 for the whole feed, not one odd row.

    Sorting compares these, and `sorted` raises on the first pair it cannot
    compare — so an unparseable value, or a naive one among aware ones, takes
    the book down.
    """

    def test_a_timestamp_without_an_offset_is_read_as_utc(self):
        page = post_page()
        page["created_time"] = "2026-03-01T12:00:00.000"
        created = POSTS.to_domain(page).created_at
        assert created.tzinfo is not None
        assert created == datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

    def test_an_unparseable_timestamp_becomes_none_rather_than_raising(self):
        page = post_page()
        page["created_time"] = "last tuesday"
        assert POSTS.to_domain(page).created_at is None

    def test_a_non_string_timestamp_becomes_none_rather_than_raising(self):
        page = post_page()
        page["created_time"] = 1772366400
        assert POSTS.to_domain(page).created_at is None

    def test_a_normal_timestamp_still_parses(self):
        assert POSTS.to_domain(post_page()).created_at == datetime(
            2026, 3, 1, 12, 0, tzinfo=timezone.utc
        )


class TestPostDeletedFlag:
    """Notion renamed the trashed flag in API version 2025-09-03.

    `_set_trashed` already falls back to the old spelling when writing, so a
    workspace on either version can be read back correctly. Only the write side
    was covered."""

    def test_a_page_in_the_trash_is_deleted(self):
        page = post_page()
        page["in_trash"] = True
        assert POSTS.to_domain(page).is_deleted is True

    def test_the_pre_2025_09_03_archived_spelling_is_honoured(self):
        page = post_page()
        page.pop("in_trash", None)
        page["archived"] = True
        assert POSTS.to_domain(page).is_deleted is True

    def test_a_page_that_says_nothing_about_the_trash_is_not_deleted(self):
        page = post_page()
        page.pop("in_trash", None)
        assert POSTS.to_domain(page).is_deleted is False


class TestPostProperties:
    def base(self, **overrides) -> Post:
        return Post(
            **{
                "id": PostId("post-1"),
                "book_id": BookId("book-1"),
                "member": MemberName("Ada"),
                "type": PostType.THOUGHT,
                "body_preview": "A thought.",
                "position": Position(9, 204),
                **overrides,
            }
        )

    def test_position_becomes_chapter_and_page(self):
        properties = POSTS.to_properties(self.base())
        assert properties["Chapter"] == {"number": 9}
        assert properties["Page"] == {"number": 204}

    # Same reason as BookMapper above: omitting a property is how a page
    # number becomes impossible to clear.
    def test_a_position_without_a_page_writes_a_null_page(self):
        properties = POSTS.to_properties(self.base(position=Position(9)))
        assert properties["Page"] == {"number": None}

    def test_no_position_writes_both_as_null(self):
        properties = POSTS.to_properties(self.base(position=None))
        assert properties["Chapter"] == {"number": None}
        assert properties["Page"] == {"number": None}

    def test_a_top_level_post_writes_an_empty_parent_post_id(self):
        properties = POSTS.to_properties(self.base())
        assert properties["Parent Post ID"] == {"rich_text": []}

    def test_a_reply_writes_its_parent_post_id(self):
        properties = POSTS.to_properties(
            self.base(parent_post_id=PostId("p9"), type=PostType.REPLY)
        )
        assert properties["Parent Post ID"]["rich_text"][0]["text"]["content"] == "p9"

    def test_the_generated_name_includes_the_chapter(self):
        """For the owner's eyes inside Notion. Never parsed back."""
        assert POSTS.label(self.base()) == "Ada · Ch 9 · Thought"

    def test_the_generated_name_without_a_chapter_omits_it(self):
        assert POSTS.label(self.base(position=None)) == "Ada · Thought"

    def test_the_round_trip_preserves_the_post(self):
        post = self.base(has_full_body=True, position=Position(12, 301))
        page = {
            "id": "post-1",
            "created_time": "2026-03-01T12:00:00.000Z",
            "last_edited_time": "2026-03-01T12:00:00.000Z",
            "properties": POSTS.to_properties(post),
        }
        restored = POSTS.to_domain(page)
        assert restored.position == post.position
        assert restored.member == post.member
        assert restored.has_full_body is True
        assert restored.body_preview == post.body_preview
