"""Notion-backed repositories.

Long bodies go into **one** paragraph block, not many. A rich text array holds
100 objects of 2000 characters, so one block covers ~200,000 — and editing a
long post becomes a single PATCH instead of deleting N blocks and appending N
at 2.5 requests/second.
"""

from __future__ import annotations

import logging
from typing import Any

from app.adapters.notion import rich_text
from app.adapters.notion.mappers import BookMapper, PostMapper, POST_BOOK
from app.domain.entities import Book, Post
from app.domain.values import BookId, PostId
from app.ports.repositories import BookRepository, PostRepository

logger = logging.getLogger(__name__)

PAGE_SIZE = 100

#: Each cursor fetch is a separate billed request, so a runaway loop is how
#: this app hits the rate limit. 5 pages is 500 posts per book.
MAX_PAGES = 5


class NotionBookRepository(BookRepository):
    def __init__(self, client, data_source_id: str, compensations) -> None:
        self._client = client
        self._data_source_id = data_source_id
        self._compensations = compensations
        self._mapper = BookMapper()

    async def list_all(self) -> list[Book]:
        pages = await _query(self._client, self._data_source_id, filter_=None)
        return [self._mapper.to_domain(page) for page in pages]

    async def get(self, book_id: BookId) -> Book | None:
        page = await _get_page(self._client, book_id.value)
        return self._mapper.to_domain(page) if page else None

    async def add(self, book: Book) -> Book:
        page = await self._client.post(
            "/pages",
            {
                # The parent is the DATA SOURCE id, not the database id.
                "parent": {
                    "type": "data_source_id",
                    "data_source_id": self._data_source_id,
                },
                "properties": self._mapper.to_properties(book),
            },
        )
        self._compensations.push_archive_page(page["id"])
        return self._mapper.to_domain(page)

    async def update(self, book: Book) -> Book:
        await self._compensations.capture_properties(book.id.value)
        page = await self._client.patch(
            f"/pages/{book.id.value}",
            {"properties": self._mapper.to_properties(book)},
        )
        return self._mapper.to_domain(page)


class NotionPostRepository(PostRepository):
    def __init__(self, client, data_source_id: str, compensations) -> None:
        self._client = client
        self._data_source_id = data_source_id
        self._compensations = compensations
        self._mapper = PostMapper()

    async def list_for_book(self, book_id: BookId) -> list[Post]:
        # Top-level posts and replies come back together in one query. Notion
        # excludes trashed pages from query results by default, so no archived
        # filter is sent — a test pins that behaviour.
        pages = await _query(
            self._client,
            self._data_source_id,
            filter_={"property": POST_BOOK, "relation": {"contains": book_id.value}},
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
        )
        return [self._mapper.to_domain(page) for page in pages]

    async def get(self, post_id: PostId) -> Post | None:
        page = await _get_page(self._client, post_id.value)
        return self._mapper.to_domain(page) if page else None

    async def add(self, post: Post, full_body: str | None = None) -> Post:
        page = await self._client.post(
            "/pages",
            {
                "parent": {
                    "type": "data_source_id",
                    "data_source_id": self._data_source_id,
                },
                "properties": self._mapper.to_properties(post),
            },
        )
        self._compensations.push_archive_page(page["id"])

        if post.has_full_body and full_body is not None:
            await self._append_body_block(page["id"], full_body)

        return self._mapper.to_domain(page)

    async def update(self, post: Post, full_body: str | None = None) -> Post:
        await self._compensations.capture_properties(post.id.value)
        page = await self._client.patch(
            f"/pages/{post.id.value}",
            {"properties": self._mapper.to_properties(post)},
        )

        # The four transitions. An implementation that handles only
        # short→short and long→long passes a naive review and fails the
        # contract suite.
        existing = await self._body_block_id(post.id.value)
        wants_block = post.has_full_body and full_body is not None

        if wants_block and existing is None:
            await self._append_body_block(post.id.value, full_body)
        elif wants_block:
            await self._client.patch(
                f"/blocks/{existing}",
                {"paragraph": {"rich_text": rich_text.to_rich_text(full_body)}},
            )
        elif existing is not None:
            await self._client.delete(f"/blocks/{existing}")

        return self._mapper.to_domain(page)

    async def archive(self, post_id: PostId) -> None:
        await _set_trashed(self._client, post_id.value, True)
        self._compensations.push_restore_page(post_id.value)

    async def get_full_body(self, post_id: PostId) -> str:
        post = await self.get(post_id)
        if post is None:
            raise KeyError(f"no such post: {post_id}")
        if not post.has_full_body:
            return post.body_preview

        blocks = await self._client.get(
            f"/blocks/{post_id.value}/children?page_size={PAGE_SIZE}"
        )
        return "".join(
            rich_text.from_rich_text(block.get("paragraph", {}).get("rich_text"))
            for block in blocks.get("results", [])
            if block.get("type") == "paragraph"
        )

    async def _append_body_block(self, page_id: str, body: str) -> None:
        response = await self._client.patch(
            f"/blocks/{page_id}/children",
            {
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": rich_text.to_rich_text(body)},
                    }
                ]
            },
        )
        for block in response.get("results", []):
            self._compensations.push_delete_block(block["id"])

    async def _body_block_id(self, page_id: str) -> str | None:
        blocks = await self._client.get(
            f"/blocks/{page_id}/children?page_size={PAGE_SIZE}"
        )
        for block in blocks.get("results", []):
            if block.get("type") == "paragraph":
                return block["id"]
        return None


async def _get_page(client, page_id: str) -> dict[str, Any] | None:
    from app.adapters.notion.http import NotionApiError

    try:
        return await client.get(f"/pages/{page_id}")
    except NotionApiError as error:
        if error.status == 404:
            return None
        raise


async def _set_trashed(client, page_id: str, trashed: bool) -> None:
    from app.adapters.notion.http import NotionApiError

    try:
        await client.patch(f"/pages/{page_id}", {"in_trash": trashed})
    except NotionApiError as error:
        if error.status != 400:
            raise
        # `archived` is the pre-2025-09-03 spelling. Kept as a fallback so an
        # older workspace does not break deletion outright.
        await client.patch(f"/pages/{page_id}", {"archived": trashed})


async def _query(
    client,
    data_source_id: str,
    filter_: dict[str, Any] | None,
    sorts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: str | None = None

    for page_number in range(MAX_PAGES):
        payload: dict[str, Any] = {"page_size": PAGE_SIZE}
        if filter_ is not None:
            payload["filter"] = filter_
        if sorts is not None:
            payload["sorts"] = sorts
        if cursor is not None:
            payload["start_cursor"] = cursor

        response = await client.post(
            f"/data_sources/{data_source_id}/query", payload
        )
        results.extend(response.get("results", []))

        cursor = response.get("next_cursor")
        if not response.get("has_more") or not cursor:
            return results

    logger.warning(
        "query hit the %d-page cap (%d rows); older rows are not being returned",
        MAX_PAGES,
        len(results),
    )
    return results
