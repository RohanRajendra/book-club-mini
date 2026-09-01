"""In-memory implementations of every port.

Real transactional semantics: `__aenter__` snapshots state, `rollback()`
restores it. That makes the fake a strict superset of Notion's behaviour rather
than a different one, which is what lets the contract suite name exactly where
the two legitimately diverge.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.domain.entities import Book, Post
from app.domain.values import BookId, PostId
from app.ports.repositories import BookRepository, PostRepository
from app.ports.unit_of_work import UnitOfWork


class _State:
    """The store. Archived posts are flagged, not deleted — Notion behaves that
    way, and a fake that hard-deletes would let a bug through."""

    def __init__(self) -> None:
        self.books: dict[str, Book] = {}
        self.posts: dict[str, Post] = {}
        self.archived: set[str] = set()
        self.full_bodies: dict[str, str] = {}
        #: Every repository call against this store, for the tests that assert
        #: a request was *not* made. It lives on the store rather than on the
        #: repository so that a log survives across units of work — otherwise
        #: "did that second feed request hit the database" is unanswerable,
        #: and the test asserting it passes vacuously.
        self.calls: list[tuple[str, str]] = []

    def snapshot(self) -> "_State":
        clone = _State()
        clone.books = dict(self.books)
        clone.posts = dict(self.posts)
        clone.archived = set(self.archived)
        clone.full_bodies = dict(self.full_bodies)
        # Deliberately shared, not copied: a rollback does not un-ask a question.
        clone.calls = self.calls
        return clone

    def restore(self, snapshot: "_State") -> None:
        self.books = dict(snapshot.books)
        self.posts = dict(snapshot.posts)
        self.archived = set(snapshot.archived)
        self.full_bodies = dict(snapshot.full_bodies)


class InMemoryBookRepository(BookRepository):
    def __init__(self, state: _State, clock: Callable[[], datetime]) -> None:
        self._state = state
        self._clock = clock

    async def list_all(self) -> list[Book]:
        return list(self._state.books.values())

    async def get(self, book_id: BookId) -> Book | None:
        return self._state.books.get(book_id.value)

    async def add(self, book: Book) -> Book:
        stored = replace(book, id=book.id or BookId(str(uuid4())))
        self._state.books[stored.id.value] = stored
        return stored

    async def update(self, book: Book) -> Book:
        if book.id is None or book.id.value not in self._state.books:
            raise KeyError(f"no such book: {book.id}")
        self._state.books[book.id.value] = book
        return book


class InMemoryPostRepository(PostRepository):
    def __init__(self, state: _State, clock: Callable[[], datetime]) -> None:
        self._state = state
        self._clock = clock

    @property
    def calls(self) -> list[tuple[str, str]]:
        """Every call against this store, shared across units of work."""
        return self._state.calls

    async def list_for_book(self, book_id: BookId) -> list[Post]:
        self._state.calls.append(("list_for_book", book_id.value))
        # Insertion order stands in for creation order and breaks a tie, which
        # a plain sort on created_at would resolve the wrong way round: two
        # posts can share a timestamp, and newest-first has to hold inside a
        # tie as well as across one.
        posts = [
            (index, post)
            for index, post in enumerate(self._state.posts.values())
            if post.book_id == book_id and post.id.value not in self._state.archived
        ]
        posts.sort(key=lambda pair: (pair[1].created_at, pair[0]), reverse=True)
        return [self._flagged(post) for _, post in posts]

    async def list_replies(self, parent_post_id: PostId) -> list[Post]:
        self._state.calls.append(("list_replies", parent_post_id.value))
        return [
            self._flagged(post)
            for post in self._state.posts.values()
            if post.parent_post_id == parent_post_id
            and post.id.value not in self._state.archived
        ]

    def _flagged(self, post: Post) -> Post:
        """The archived set is what says a post is deleted, not the stored
        record — so an `update` cannot resurrect one by writing the flag."""
        return replace(post, is_deleted=post.id.value in self._state.archived)

    async def get(self, post_id: PostId) -> Post | None:
        self._state.calls.append(("get", post_id.value))
        post = self._state.posts.get(post_id.value)
        return self._flagged(post) if post is not None else None

    async def add(self, post: Post, full_body: str | None = None) -> Post:
        self._state.calls.append(("add", str(post.id)))
        now = self._clock()
        stored = replace(
            post,
            id=post.id or PostId(str(uuid4())),
            created_at=post.created_at or now,
            edited_at=post.edited_at or now,
        )
        self._state.posts[stored.id.value] = stored
        self._write_full_body(stored, full_body)
        return stored

    async def update(self, post: Post, full_body: str | None = None) -> Post:
        self._state.calls.append(("update", str(post.id)))
        if post.id is None or post.id.value not in self._state.posts:
            raise KeyError(f"no such post: {post.id}")
        stored = replace(post, edited_at=self._clock())
        self._state.posts[stored.id.value] = stored
        self._write_full_body(stored, full_body)
        return stored

    async def archive(self, post_id: PostId) -> None:
        self._state.calls.append(("archive", post_id.value))
        if post_id.value not in self._state.posts:
            raise KeyError(f"no such post: {post_id}")
        self._state.archived.add(post_id.value)

    async def get_full_body(self, post_id: PostId) -> str:
        self._state.calls.append(("get_full_body", post_id.value))
        post = self._state.posts.get(post_id.value)
        if post is None:
            raise KeyError(f"no such post: {post_id}")
        return self._state.full_bodies.get(post_id.value, post.body_preview)

    def _write_full_body(self, post: Post, full_body: str | None) -> None:
        """Mirrors the four transitions the Notion adapter has to handle:
        short→short, short→long, long→long, long→short."""
        if post.has_full_body and full_body is not None:
            self._state.full_bodies[post.id.value] = full_body
        else:
            self._state.full_bodies.pop(post.id.value, None)


class InMemoryUnitOfWork(UnitOfWork):
    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        state: _State | None = None,
    ) -> None:
        # Tests that assert on ordering need control of time, and a hidden
        # now() call is the usual reason those tests turn flaky.
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._state = state if state is not None else _State()
        self._snapshot: _State | None = None
        self.books = InMemoryBookRepository(self._state, self._clock)
        self.posts = InMemoryPostRepository(self._state, self._clock)
        self.on_commit: list[Callable[[], None]] = []

    async def __aenter__(self) -> "InMemoryUnitOfWork":
        self._snapshot = self._state.snapshot()
        await super().__aenter__()
        return self

    async def _commit(self) -> None:
        self._snapshot = None
        self._fire_on_commit()

    async def rollback(self) -> None:
        if self._snapshot is not None:
            self._state.restore(self._snapshot)
            self._snapshot = None


def in_memory_uow_factory(
    clock: Callable[[], datetime] | None = None,
) -> Callable[[], InMemoryUnitOfWork]:
    """A factory whose units of work share one store, so `commit()` in one
    scope is visible in the next."""
    state = _State()
    return lambda: InMemoryUnitOfWork(clock=clock, state=state)
