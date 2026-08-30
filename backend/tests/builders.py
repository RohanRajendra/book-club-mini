"""Builders, not fixture soup.

Every field is defaulted so a test states only what it cares about. A test that
sets eight fields to assert one is hiding its own point.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.entities import Book, Post
from app.domain.values import BookId, BookStatus, MemberName, Position, PostId, PostType

ADA = MemberName("Ada")
GRACE = MemberName("Grace")
ROSTER = [ADA, GRACE]

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def at_minute(minute: int) -> datetime:
    return EPOCH + timedelta(minutes=minute)


def make_book(**overrides) -> Book:
    return Book(
        **{
            "id": BookId("book-1"),
            "title": "Piranesi",
            "author": "Susanna Clarke",
            "status": BookStatus.CURRENTLY_READING,
            "total_chapters": 30,
            **overrides,
        }
    )


def make_post(**overrides) -> Post:
    created = overrides.pop("created_at", EPOCH)
    return Post(
        **{
            "id": PostId("post-1"),
            "book_id": BookId("book-1"),
            "member": ADA,
            "type": PostType.THOUGHT,
            "body_preview": "A thought about the statues.",
            "has_full_body": False,
            "position": Position(9, 204),
            "parent_post_id": None,
            "created_at": created,
            "edited_at": overrides.pop("edited_at", created),
            **overrides,
        }
    )


def make_progress(member: MemberName, chapter: int, page: int | None = None, **overrides) -> Post:
    return make_post(
        member=member,
        type=PostType.PROGRESS,
        position=Position(chapter, page),
        body_preview=overrides.pop("body_preview", ""),
        **overrides,
    )


def make_reply(parent: Post, member: MemberName, **overrides) -> Post:
    """Copies the parent's position and sets parent_post_id and type.

    The rule lives in one place in the tests, mirroring the use case that
    enforces it.
    """
    return make_post(
        book_id=parent.book_id,
        member=member,
        type=PostType.REPLY,
        parent_post_id=parent.id,
        position=parent.position,
        body_preview=overrides.pop("body_preview", "A reply."),
        **overrides,
    )


def long_body(length: int = 4000) -> str:
    """A body comfortably over the 1900-character preview limit."""
    sentence = "The house is the world and the world is the house. "
    return (sentence * (length // len(sentence) + 1))[:length]
