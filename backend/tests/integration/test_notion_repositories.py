"""Assert on the outbound request as much as the parsed response.

The failure mode this catches is sending a database ID where a data source ID
belongs, and only a request assertion sees it — a response mock would happily
return success either way.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.notion.http import BASE_URL, NOTION_VERSION, NotionHttpClient, TokenBucket
from app.application.use_cases.delete_post import DeletePost, DeletePostCommand
from app.adapters.notion.repositories import MAX_PAGES, PAGE_SIZE
from app.adapters.notion.unit_of_work import NotionUnitOfWork
from app.domain.entities import Book, Post
from app.domain.values import BookId, MemberName, Position, PostId, PostType
from tests.builders import ADA, long_body, make_post, make_reply
from tests.integration.notion_stub import BOOKS_DB, BOOKS_DS, POSTS_DS, NotionStub

BOOK = BookId("book-page-id")


class NoWait:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1.0
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def stub():
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        stub = NotionStub()
        router.route().mock(side_effect=stub.handler)
        yield stub


@pytest.fixture
def uow(stub):
    timing = NoWait()
    client = NotionHttpClient(
        token="ntn_test",
        client=httpx.AsyncClient(base_url=BASE_URL),
        bucket=TokenBucket(clock=timing, sleep=timing.sleep),
        sleep=timing.sleep,
    )
    return NotionUnitOfWork(client, BOOKS_DS, POSTS_DS)


async def test_query_hits_the_data_source_endpoint_not_the_database_endpoint(uow, stub):
    """This API's signature mistake. Only a request assertion sees it."""
    async with uow:
        await uow.posts.list_for_book(BOOK)

    assert f"/data_sources/{POSTS_DS}/query" in stub.paths("POST")
    assert not [path for path in stub.paths() if path.startswith("/databases/")]


async def test_page_creation_sends_parent_type_data_source_id(uow, stub):
    async with uow:
        await uow.posts.add(make_post(id=None, book_id=BOOK))

    payload = next(body for verb, path, body in stub.requests if path == "/pages")
    assert payload["parent"] == {
        "type": "data_source_id",
        "data_source_id": POSTS_DS,
    }


async def test_every_request_carries_the_notion_version(uow, stub):
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        route = router.route().mock(side_effect=stub.handler)
        async with uow:
            await uow.posts.list_for_book(BOOK)
        assert all(
            call.request.headers["Notion-Version"] == NOTION_VERSION
            for call in route.calls
        )


async def test_the_query_filters_on_the_book_relation(uow, stub):
    async with uow:
        await uow.posts.list_for_book(BOOK)

    payload = next(
        body for verb, path, body in stub.requests if path.endswith("/query")
    )
    assert payload["filter"] == {
        "property": "Book",
        "relation": {"contains": BOOK.value},
    }
    assert payload["sorts"] == [
        {"timestamp": "created_time", "direction": "descending"}
    ]


async def test_the_query_sends_no_archived_filter(uow, stub):
    """Notion excludes trashed pages by default. Pinned so a future filter
    change does not silently start returning deleted posts."""
    async with uow:
        await uow.posts.list_for_book(BOOK)

    payload = next(
        body for verb, path, body in stub.requests if path.endswith("/query")
    )
    assert "archived" not in str(payload)
    assert "in_trash" not in str(payload)


async def test_archived_pages_are_absent_from_query_results(uow):
    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        await uow.posts.archive(post.id)
        assert await uow.posts.list_for_book(BOOK) == []


async def test_pagination_follows_next_cursor(uow, stub):
    async with uow:
        for _ in range(PAGE_SIZE + 5):
            await uow.posts.add(make_post(id=None, book_id=BOOK))
        stub.requests.clear()
        listed = await uow.posts.list_for_book(BOOK)

    assert len(listed) == PAGE_SIZE + 5
    queries = [body for verb, path, body in stub.requests if path.endswith("/query")]
    assert len(queries) == 2
    assert queries[1]["start_cursor"] == str(PAGE_SIZE)


async def test_pagination_stops_at_the_page_cap_and_warns(uow, stub, caplog):
    async with uow:
        for _ in range(PAGE_SIZE * MAX_PAGES + 1):
            await uow.posts.add(make_post(id=None, book_id=BOOK))
        stub.requests.clear()
        with caplog.at_level("WARNING"):
            listed = await uow.posts.list_for_book(BOOK)

    assert len(listed) == PAGE_SIZE * MAX_PAGES
    assert len([b for v, p, b in stub.requests if p.endswith("/query")]) == MAX_PAGES
    assert "page cap" in caplog.text


async def test_the_delete_cascade_reaches_a_reply_beyond_the_page_cap(uow, stub):
    """The cascade found replies by scanning `list_for_book`, which stops at
    500 rows. A reply older than that survived its parent and then vanished:
    feed assembly drops a reply whose parent is missing, so it was invisible
    forever while still counting against the query budget."""
    async with uow:
        parent = await uow.posts.add(make_post(id=None, book_id=BOOK, member=ADA))
        reply = await uow.posts.add(make_reply(parent, ADA, id=None))
        # Newest-first, so these push the pair off the end of the last page.
        for _ in range(PAGE_SIZE * MAX_PAGES):
            await uow.posts.add(make_post(id=None, book_id=BOOK))

        assert parent.id not in {post.id for post in await uow.posts.list_for_book(BOOK)}

    result = await DeletePost(uow_factory=lambda: uow).execute(
        DeletePostCommand(post_id=parent.id, member=ADA)
    )

    assert result.unwrap() == 2
    assert stub.pages[reply.id.value]["in_trash"] is True


async def test_long_post_creation_sends_a_page_write_and_a_block_append(uow, stub):
    body = long_body(4000)
    async with uow:
        await uow.posts.add(
            make_post(id=None, book_id=BOOK, body_preview=body[:1900], has_full_body=True),
            body,
        )

    assert "/pages" in stub.paths("POST")
    assert any(path.endswith("/children") for path in stub.paths("PATCH"))


async def test_a_long_body_becomes_one_block_not_many(uow, stub):
    """One block covers ~200,000 characters, and editing it is a single PATCH
    instead of deleting N blocks and appending N at 2.5 requests/second."""
    body = long_body(150_000)
    async with uow:
        post = await uow.posts.add(
            make_post(id=None, book_id=BOOK, body_preview=body[:1900], has_full_body=True),
            body,
        )
    assert len(stub.blocks[post.id.value]) == 1


async def test_short_post_creation_sends_no_block_append(uow, stub):
    async with uow:
        await uow.posts.add(make_post(id=None, book_id=BOOK, body_preview="Short."))
    assert not [path for path in stub.paths("PATCH") if path.endswith("/children")]


class TestUpdateTransitions:
    """The four transitions. An implementation that handles only short→short
    and long→long passes a naive review and fails these."""

    async def make_post(self, uow, *, long: bool):
        body = long_body(4000) if long else None
        return await uow.posts.add(
            make_post(
                id=None,
                book_id=BOOK,
                body_preview=(body[:1900] if long else "Short."),
                has_full_body=long,
            ),
            body,
        )

    def rewrite(self, post: Post, *, preview: str, has_full: bool) -> Post:
        return Post(
            id=post.id,
            book_id=post.book_id,
            member=post.member,
            type=post.type,
            body_preview=preview,
            has_full_body=has_full,
            position=post.position,
            created_at=post.created_at,
        )

    async def test_update_short_to_short_touches_no_block(self, uow, stub):
        async with uow:
            post = await self.make_post(uow, long=False)
            stub.requests.clear()
            await uow.posts.update(
                self.rewrite(post, preview="Still short.", has_full=False)
            )
        assert not [p for p in stub.paths("DELETE")]
        assert not [p for p in stub.paths("PATCH") if p.endswith("/children")]

    async def test_update_short_to_long_appends_a_block(self, uow, stub):
        body = long_body(4000)
        async with uow:
            post = await self.make_post(uow, long=False)
            stub.requests.clear()
            await uow.posts.update(
                self.rewrite(post, preview=body[:1900], has_full=True), body
            )
            assert await uow.posts.get_full_body(post.id) == body
        assert any(p.endswith("/children") for p in stub.paths("PATCH"))

    async def test_update_long_to_long_patches_the_existing_block(self, uow, stub):
        second = long_body(3000).replace("house", "labyrinth")
        async with uow:
            post = await self.make_post(uow, long=True)
            block_id = stub.blocks[post.id.value][0]["id"]
            stub.requests.clear()
            await uow.posts.update(
                self.rewrite(post, preview=second[:1900], has_full=True), second
            )
            assert await uow.posts.get_full_body(post.id) == second

        assert f"/blocks/{block_id}" in stub.paths("PATCH")
        assert len(stub.blocks[post.id.value]) == 1
        assert not stub.paths("DELETE")

    async def test_update_long_to_short_sends_a_block_delete(self, uow, stub):
        async with uow:
            post = await self.make_post(uow, long=True)
            block_id = stub.blocks[post.id.value][0]["id"]
            stub.requests.clear()
            await uow.posts.update(
                self.rewrite(post, preview="Now short.", has_full=False)
            )
            assert await uow.posts.get_full_body(post.id) == "Now short."

        assert f"/blocks/{block_id}" in stub.paths("DELETE")
        assert stub.blocks[post.id.value] == []


async def test_archive_sends_in_trash(uow, stub):
    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        stub.requests.clear()
        await uow.posts.archive(post.id)

    payload = next(body for verb, path, body in stub.requests if verb == "PATCH")
    assert payload == {"in_trash": True}


async def test_archive_falls_back_to_archived_when_in_trash_is_rejected(uow, stub):
    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        stub.fail_next["patch_page"] = 400
        stub.requests.clear()
        await uow.posts.archive(post.id)

    payloads = [body for verb, path, body in stub.requests if verb == "PATCH"]
    assert payloads == [{"in_trash": True}, {"archived": True}]
    assert stub.pages[post.id.value]["in_trash"] is True


async def test_an_archive_failure_that_is_not_a_400_is_not_retried_as_archived(uow, stub):
    """The `archived` fallback exists for a workspace that rejects `in_trash`.
    A 403 is a permissions problem and must surface, not be papered over."""
    from app.adapters.notion.http import NotionApiError

    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        stub.fail_next["patch_page"] = 403
        stub.requests.clear()
        with pytest.raises(NotionApiError):
            await uow.posts.archive(post.id)

    assert [body for verb, path, body in stub.requests if verb == "PATCH"] == [
        {"in_trash": True}
    ]


async def test_getting_a_missing_page_returns_none_rather_than_raising(uow):
    async with uow:
        assert await uow.posts.get(PostId("does-not-exist")) is None
        assert await uow.books.get(BookId("does-not-exist")) is None


async def test_get_full_body_on_a_missing_post_raises(uow):
    async with uow:
        with pytest.raises(KeyError):
            await uow.posts.get_full_body(PostId("does-not-exist"))


async def test_books_are_listed_from_the_books_data_source(uow, stub):
    async with uow:
        await uow.books.add(Book(title="Piranesi"))
        stub.requests.clear()
        books = await uow.books.list_all()

    assert [book.title for book in books] == ["Piranesi"]
    assert f"/data_sources/{BOOKS_DS}/query" in stub.paths("POST")
