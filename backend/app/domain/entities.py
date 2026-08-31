"""Entities: Book and Post.

These guards enforce the invariants that must hold *everywhere*. Rules that
depend on another object — that a reply's parent is not itself a reply, that a
parent shares the reply's book — belong to the use cases. The entity cannot see
the parent.

The guards raise `ValueError`, which is not how expected failures are reported.
That is deliberate: use cases validate input and return `Err` before constructing
anything, and these remain as last-line assertions against a programming error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.values import BookId, BookStatus, MemberName, Position, PostId, PostType

#: Notion's rich text property caps at 2000 characters. The margin keeps
#: truncation from colliding with the limit (00-overview.md §Notion schema).
PREVIEW_LIMIT = 1900

#: Below this, a difference between created_at and last_edited_time is the
#: write path talking, not a member. Creating a long post is a page write then a
#: block append, and the append bumps last_edited_time.
EDIT_THRESHOLD = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class Book:
    title: str
    id: BookId | None = None
    author: str | None = None
    status: BookStatus = BookStatus.UPCOMING
    total_chapters: int | None = None

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("a book needs a title")
        if self.total_chapters is not None and self.total_chapters < 1:
            raise ValueError(
                f"total_chapters must be 1 or greater, got {self.total_chapters}"
            )

    def contains_chapter(self, chapter: int) -> bool:
        """Whether a chapter number fits inside this book.

        The book is the only thing that knows its own length, so the rule lives
        here rather than in a service. A book that states no length accepts any
        chapter — demanding a chapter count before the app is usable was
        rejected deliberately, and an unknown length cannot exclude anything.
        """
        return self.total_chapters is None or chapter <= self.total_chapters


@dataclass(frozen=True, slots=True)
class Post:
    book_id: BookId
    member: MemberName
    type: PostType
    body_preview: str = ""
    has_full_body: bool = False
    position: Position | None = None
    parent_post_id: PostId | None = None
    id: PostId | None = None
    created_at: datetime | None = None
    edited_at: datetime | None = None
    #: Set by the store on read, never by a use case. A deleted post is
    #: archived rather than destroyed and stays retrievable by id, so this is
    #: the only thing that distinguishes it from a live one.
    is_deleted: bool = False

    def __post_init__(self) -> None:
        if len(self.body_preview) > PREVIEW_LIMIT:
            raise ValueError(
                f"body_preview must be at most {PREVIEW_LIMIT} characters, "
                f"got {len(self.body_preview)}"
            )
        if self.parent_post_id is not None and self.type is not PostType.REPLY:
            raise ValueError(
                "a post with a parent_post_id must have type Reply; "
                f"got {self.type.value}"
            )
        if self.type is PostType.PROGRESS and self.position is None:
            raise ValueError("a Progress post requires a position")

    @property
    def is_reply(self) -> bool:
        return self.parent_post_id is not None

    @property
    def was_edited(self) -> bool:
        """Whether a member changed this post after posting it.

        Compared against a threshold rather than for equality, because the
        create-then-append write path moves last_edited_time on its own.
        """
        if self.created_at is None or self.edited_at is None:
            return False
        return self.edited_at - self.created_at > EDIT_THRESHOLD
