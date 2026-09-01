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

    #: Whether `commit()` was reached inside the current scope.
    _committed: bool = False

    async def __aenter__(self) -> "UnitOfWork":
        self._committed = False
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Roll back unless the scope committed.

        Still no auto-commit: an implicit commit on a use case that returned
        `Err` is a bug waiting to happen, so use cases commit explicitly.

        But leaving uncommitted writes in place is the same bug from the other
        side. Only an exception used to trigger a rollback, so a use case that
        wrote and then returned `Err` — one added guard clause away — left
        those writes durable and unannounced. A scope that did not commit did
        not succeed, however it ended.
        """
        if not self._committed:
            await self.rollback()

    async def commit(self) -> None:
        """Final, so that no implementation can forget to record the fact.

        Implementations override `_commit`. That is what makes rollback-unless-
        committed a property of the port rather than a convention each adapter
        has to remember.
        """
        await self._commit()
        self._committed = True

    @abstractmethod
    async def _commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

    def _fire_on_commit(self) -> None:
        for callback in self.on_commit:
            callback()
