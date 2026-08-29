"""Notion page dicts ↔ domain entities.

Notion's property names and shapes are the most fragile knowledge in the
codebase. They are module-level constants here and **nowhere else** — an
architecture test enforces that no Notion property name appears outside this
package.

`to_domain` is forgiving on purpose. The owner edits these rows by hand in
Notion, and a hand-edit must not 500 the app.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.adapters.notion import rich_text
from app.domain.entities import Book, Post
from app.domain.values import BookId, BookStatus, MemberName, Position, PostId, PostType

# --- Books ------------------------------------------------------------------
BOOK_TITLE = "Title"
BOOK_AUTHOR = "Author"
BOOK_STATUS = "Status"
BOOK_TOTAL_CHAPTERS = "Total Chapters"

# --- Posts ------------------------------------------------------------------
POST_NAME = "Name"
POST_BOOK = "Book"
POST_MEMBER = "Member"
POST_TYPE = "Type"
POST_BODY_PREVIEW = "Body Preview"
POST_HAS_FULL_BODY = "Has Full Body"
POST_CHAPTER = "Chapter"
POST_PAGE = "Page"
POST_PARENT_ID = "Parent Post ID"


def _timestamp(page: dict[str, Any], key: str) -> datetime | None:
    raw = page.get(key)
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class BookMapper:
    def to_domain(self, page: dict[str, Any]) -> Book:
        properties = page.get("properties", {})

        raw_status = rich_text.select_name(properties, BOOK_STATUS)
        try:
            status = BookStatus(raw_status)
        except ValueError:
            # An unrecognised status is a hand-edit, not a crash.
            status = BookStatus.UPCOMING

        total = rich_text.number(properties, BOOK_TOTAL_CHAPTERS)

        return Book(
            id=BookId(page["id"]),
            title=rich_text.plain(properties, BOOK_TITLE) or "Untitled",
            author=rich_text.plain(properties, BOOK_AUTHOR) or None,
            status=status,
            total_chapters=total if total and total > 0 else None,
        )

    def to_properties(self, book: Book) -> dict[str, Any]:
        properties: dict[str, Any] = {
            BOOK_TITLE: {"title": rich_text.to_rich_text(book.title)},
            BOOK_STATUS: {"select": {"name": book.status.value}},
        }
        if book.author is not None:
            properties[BOOK_AUTHOR] = {
                "rich_text": rich_text.to_rich_text(book.author)
            }
        if book.total_chapters is not None:
            properties[BOOK_TOTAL_CHAPTERS] = {"number": book.total_chapters}
        return properties


class PostMapper:
    def to_domain(self, page: dict[str, Any]) -> Post:
        properties = page.get("properties", {})

        raw_type = rich_text.select_name(properties, POST_TYPE)
        try:
            post_type = PostType(raw_type)
        except ValueError:
            post_type = PostType.THOUGHT

        chapter = rich_text.number(properties, POST_CHAPTER)
        page_number = rich_text.number(properties, POST_PAGE)
        position = (
            Position(chapter, page_number if page_number and page_number > 0 else None)
            if chapter and chapter > 0
            else None
        )

        parent_raw = rich_text.plain(properties, POST_PARENT_ID).strip()
        parent_post_id = PostId(parent_raw) if parent_raw else None

        # The entity refuses a parent without type Reply, and a hand-edit in
        # Notion can produce exactly that. The parent is what makes it a reply.
        if parent_post_id is not None:
            post_type = PostType.REPLY

        # A Progress row hand-edited to have no chapter would fail the entity
        # invariant; treat it as a Thought rather than 500 the feed.
        if post_type is PostType.PROGRESS and position is None:
            post_type = PostType.THOUGHT

        book_ids = rich_text.relation_ids(properties, POST_BOOK)

        return Post(
            id=PostId(page["id"]),
            book_id=BookId(book_ids[0]) if book_ids else BookId("orphan"),
            member=MemberName(
                rich_text.select_name(properties, POST_MEMBER) or "Unknown"
            ),
            type=post_type,
            body_preview=rich_text.plain(properties, POST_BODY_PREVIEW),
            has_full_body=rich_text.checkbox(properties, POST_HAS_FULL_BODY),
            position=position,
            parent_post_id=parent_post_id,
            created_at=_timestamp(page, "created_time"),
            edited_at=_timestamp(page, "last_edited_time"),
        )

    def to_properties(self, post: Post) -> dict[str, Any]:
        properties: dict[str, Any] = {
            POST_NAME: {"title": rich_text.to_rich_text(self.label(post))},
            POST_BOOK: {"relation": [{"id": post.book_id.value}]},
            POST_MEMBER: {"select": {"name": post.member.value}},
            POST_TYPE: {"select": {"name": post.type.value}},
            POST_BODY_PREVIEW: {
                "rich_text": rich_text.to_rich_text(post.body_preview)
            },
            POST_HAS_FULL_BODY: {"checkbox": post.has_full_body},
        }
        if post.position is not None:
            properties[POST_CHAPTER] = {"number": post.position.chapter}
            if post.position.page is not None:
                properties[POST_PAGE] = {"number": post.position.page}
        if post.parent_post_id is not None:
            properties[POST_PARENT_ID] = {
                "rich_text": rich_text.to_rich_text(post.parent_post_id.value)
            }
        return properties

    @staticmethod
    def label(post: Post) -> str:
        """The `Name` title, generated for the owner's eyes inside Notion.
        Never parsed back."""
        if post.position is not None:
            return f"{post.member} · Ch {post.position.chapter} · {post.type.value}"
        return f"{post.member} · {post.type.value}"
