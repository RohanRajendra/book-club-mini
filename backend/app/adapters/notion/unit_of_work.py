"""Notion has no transactions. `rollback()` is compensating, not atomic.

As each write succeeds its inverse is pushed onto a stack, and `rollback()`
replays that stack in reverse.

| Forward operation        | Compensation                        |
|--------------------------|-------------------------------------|
| Create page              | Archive page                        |
| Append block             | Delete block                        |
| Update page properties   | Restore captured previous properties|
| Archive page             | Un-archive page                     |

This is best-effort. A compensation can itself fail, and a concurrent reader
can observe an intermediate state. Both are acceptable for two people, and both
are stated in the README. Every failed compensation is logged at ERROR with
enough detail to repair by hand.

`commit()` clears the stack — the writes are already durable by then. That is
not a bug.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.adapters.notion.repositories import NotionBookRepository, NotionPostRepository
from app.ports.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class CompensationStack:
    def __init__(self, client) -> None:
        self._client = client
        self._entries: list[tuple[str, Callable[[], Any]]] = []
        self._captured: set[str] = set()

    def push_archive_page(self, page_id: str) -> None:
        self._entries.append(
            (
                f"archive page {page_id} (created in this scope)",
                lambda: self._client.patch(f"/pages/{page_id}", {"in_trash": True}),
            )
        )

    def push_restore_page(self, page_id: str) -> None:
        self._entries.append(
            (
                f"restore page {page_id} (archived in this scope)",
                lambda: self._client.patch(f"/pages/{page_id}", {"in_trash": False}),
            )
        )

    def push_delete_block(self, block_id: str) -> None:
        self._entries.append(
            (
                f"delete block {block_id} (appended in this scope)",
                lambda: self._client.delete(f"/blocks/{block_id}"),
            )
        )

    async def capture_properties(self, page_id: str) -> None:
        """Read the properties before an update so they can be restored.

        Costs a read, so it happens once per page per scope. A single-write use
        case does not need compensation at all, and this is only reached from
        an update inside a scope that could still fail afterwards.
        """
        if page_id in self._captured:
            return
        self._captured.add(page_id)

        page = await self._client.get(f"/pages/{page_id}")
        previous = page.get("properties", {})
        self._entries.append(
            (
                f"restore properties of page {page_id}",
                lambda: self._client.patch(
                    f"/pages/{page_id}", {"properties": previous}
                ),
            )
        )

    async def replay(self) -> None:
        """Reverse order, continuing past individual failures."""
        while self._entries:
            description, undo = self._entries.pop()
            try:
                await undo()
            except Exception:
                logger.error(
                    "compensation failed, repair by hand: %s", description, exc_info=True
                )

    def clear(self) -> None:
        self._entries.clear()
        self._captured.clear()


class NotionUnitOfWork(UnitOfWork):
    """Rollback is compensating, not atomic. See the module docstring."""

    supports_transactions = False

    def __init__(self, client, books_data_source_id: str, posts_data_source_id: str) -> None:
        self._client = client
        self._compensations = CompensationStack(client)
        self.books = NotionBookRepository(
            client, books_data_source_id, self._compensations
        )
        self.posts = NotionPostRepository(
            client, posts_data_source_id, self._compensations
        )
        self.on_commit: list[Callable[[], None]] = []

    async def __aenter__(self) -> "NotionUnitOfWork":
        self._compensations.clear()
        return self

    async def commit(self) -> None:
        self._compensations.clear()
        self._fire_on_commit()

    async def rollback(self) -> None:
        await self._compensations.replay()
