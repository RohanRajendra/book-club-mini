"""Persistence ports.

Methods take and return **domain entities**, never Notion dicts. Notion's
property shapes stop at the mapper.

The two repositories stay separate even though one unit of work supplies both,
so a use case that only reads books cannot reach posts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import Book, Post
from app.domain.values import BookId, PostId


class BookRepository(ABC):
    @abstractmethod
    async def list_all(self) -> list[Book]:
        """Every book, in no guaranteed order. Ordering is a use-case concern."""

    @abstractmethod
    async def get(self, book_id: BookId) -> Book | None: ...

    @abstractmethod
    async def add(self, book: Book) -> Book:
        """Persist a new book and return it with its assigned id."""

    @abstractmethod
    async def update(self, book: Book) -> Book: ...


class PostRepository(ABC):
    """`full_body` is a separate parameter rather than a field on `Post`.

    The entity carries the preview and a `has_full_body` flag; the full text is
    a lazily-fetched detail. Keeping it off the entity is what structurally
    prevents the feed from loading bodies.
    """

    @abstractmethod
    async def list_for_book(self, book_id: BookId) -> list[Post]:
        """Every unarchived post for the book, top-level and replies together,
        newest first.

        Newest-first holds *within* a tie as well as across one. Notion
        truncates `created_time` to the minute, so two posts a moment apart
        share a timestamp routinely, and `PositionResolver` breaks that tie by
        taking the first post listed. A store whose tie order is the creation
        order reversed makes a member's mistyped chapter outlive their
        correction.
        """

    @abstractmethod
    async def list_replies(self, parent_post_id: PostId) -> list[Post]:
        """Every unarchived reply to one post.

        Separate from `list_for_book` because the delete cascade needs *all* of
        them, and a book-wide listing is capped — a reply past the cap survived
        its parent and then became invisible, since feed assembly drops a reply
        whose parent is gone. Asking for what is actually needed also stops the
        cascade paying for a whole book to find two replies.
        """

    @abstractmethod
    async def get(self, post_id: PostId) -> Post | None:
        """Retrieve by id, including archived posts, with `is_deleted` set.

        Archived posts are returned on purpose — a soft delete has to stay
        recoverable. The flag is what keeps that from making a deleted post
        indistinguishable from a live one.
        """

    @abstractmethod
    async def add(self, post: Post, full_body: str | None = None) -> Post:
        """Persist a new post and return it with its assigned id and timestamps."""

    @abstractmethod
    async def update(self, post: Post, full_body: str | None = None) -> Post: ...

    @abstractmethod
    async def archive(self, post_id: PostId) -> None:
        """Archive rather than destroy, so everything stays recoverable."""

    @abstractmethod
    async def get_full_body(self, post_id: PostId) -> str:
        """The complete body. Returns the preview when there is no full body."""
