"""The unit-of-work port.

Two operations in this app are multi-step and must not half-apply: creating a
long post (page, then block) and deleting a post (post, then each reply).

**An implementation may provide compensating rollback rather than atomicity.**
`NotionUnitOfWork` does, because Notion has no transactions: it replays inverse
operations, which is best-effort, can itself fail, and can be observed
mid-flight by a concurrent reader. `InMemoryUnitOfWork` provides real rollback.
The contract suite marks the tests that only a transactional implementation can
pass, and says why.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from app.ports.repositories import BookRepository, PostRepository


class UnitOfWork(ABC):
    books: BookRepository
    posts: PostRepository

    #: Callbacks invoked after a successful commit and never after a rollback.
    #: The container registers the feed cache's invalidation here, which is how
    #: invalidation happens in exactly one place instead of at every write site
    #:.
    on_commit: list[Callable[[], None]]

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Roll back if an exception passed through, otherwise do nothing.

        Deliberately no auto-commit: an implicit commit on a use case that
        returned `Err` is a bug waiting to happen. Use cases commit explicitly.
        """
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

    def _fire_on_commit(self) -> None:
        for callback in self.on_commit:
            callback()
