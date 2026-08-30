"""Compensating rollback.

The first test is the requirement that justified this whole pattern: a post
whose preview says "Read more" with no block behind it is worse than a post
that failed to save.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.notion.http import BASE_URL, NotionApiError, NotionHttpClient, TokenBucket
from app.adapters.notion.unit_of_work import NotionUnitOfWork
from app.domain.values import BookId
from tests.builders import ADA, GRACE, long_body, make_post, make_reply
from tests.integration.notion_stub import BOOKS_DS, POSTS_DS, NotionStub

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


async def test_failed_block_append_archives_the_page_that_was_just_created(uow, stub):
    body = long_body(4000)
    stub.fail_next["append_block"] = 400

    with pytest.raises(NotionApiError):
        async with uow:
            await uow.posts.add(
                make_post(
                    id=None, book_id=BOOK, body_preview=body[:1900], has_full_body=True
                ),
                body,
            )

    created = [page for page in stub.pages.values()]
    assert len(created) == 1
    assert created[0]["in_trash"] is True


async def test_failed_reply_archive_during_delete_leaves_the_parent_intact(uow, stub):
    async with uow:
        parent = await uow.posts.add(make_post(id=None, book_id=BOOK, member=ADA))
        reply = await uow.posts.add(make_reply(parent, GRACE, id=None))
        await uow.commit()

    with pytest.raises(NotionApiError):
        async with uow:
            await uow.posts.archive(reply.id)
            # 403, not 500: a 5xx is retried and would succeed on attempt two.
            stub.fail_next["patch_page"] = 403
            await uow.posts.archive(parent.id)

    assert stub.pages[parent.id.value]["in_trash"] is False
    assert stub.pages[reply.id.value]["in_trash"] is False


async def test_compensations_run_in_reverse_order(uow, stub):
    async with uow:
        first = await uow.posts.add(make_post(id=None, book_id=BOOK))
        second = await uow.posts.add(make_post(id=None, book_id=BOOK))
        stub.requests.clear()
        await uow.rollback()

    archived = [
        path for verb, path, body in stub.requests if body == {"in_trash": True}
    ]
    assert archived == [f"/pages/{second.id.value}", f"/pages/{first.id.value}"]


async def test_a_failing_compensation_is_logged_and_does_not_stop_the_rest(
    uow, stub, caplog
):
    async with uow:
        first = await uow.posts.add(make_post(id=None, book_id=BOOK))
        second = await uow.posts.add(make_post(id=None, book_id=BOOK))

        # The compensation for `second` runs first and will fail. 403 rather
        # than 500 because a 5xx is retried and would succeed on attempt two.
        stub.fail_next["patch_page"] = 403
        with caplog.at_level("ERROR"):
            await uow.rollback()

    assert "compensation failed, repair by hand" in caplog.text
    assert stub.pages[second.id.value]["in_trash"] is False
    assert stub.pages[first.id.value]["in_trash"] is True


async def test_commit_clears_the_compensation_stack(uow, stub):
    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        await uow.commit()
        stub.requests.clear()
        await uow.rollback()

    assert stub.requests == []
    assert stub.pages[post.id.value]["in_trash"] is False


async def test_successful_scope_performs_no_compensating_requests(uow, stub):
    async with uow:
        await uow.posts.add(make_post(id=None, book_id=BOOK))
        await uow.commit()

    assert not [body for verb, path, body in stub.requests if body == {"in_trash": True}]


async def test_rolling_back_an_update_restores_the_previous_properties(uow, stub):
    async with uow:
        post = await uow.posts.add(
            make_post(id=None, book_id=BOOK, body_preview="Original.")
        )
        await uow.commit()

    from app.domain.entities import Post

    async with uow:
        await uow.posts.update(
            Post(
                id=post.id,
                book_id=post.book_id,
                member=post.member,
                type=post.type,
                body_preview="Changed.",
                position=post.position,
                created_at=post.created_at,
            )
        )
        await uow.rollback()

    async with uow:
        assert (await uow.posts.get(post.id)).body_preview == "Original."


async def test_properties_are_captured_once_per_page_per_scope(uow, stub):
    """Capturing costs a read, so a second update to the same page in one
    scope must not pay it again."""
    from app.domain.entities import Post

    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        await uow.commit()

    def rewrite(text):
        return Post(
            id=post.id,
            book_id=post.book_id,
            member=post.member,
            type=post.type,
            body_preview=text,
            position=post.position,
            created_at=post.created_at,
        )

    async with uow:
        stub.requests.clear()
        await uow.posts.update(rewrite("One."))
        await uow.posts.update(rewrite("Two."))

    reads = [path for verb, path, _ in stub.requests if verb == "GET" and "/pages/" in path]
    assert len(reads) == 1


async def test_archiving_then_rolling_back_restores_the_post(uow, stub):
    async with uow:
        post = await uow.posts.add(make_post(id=None, book_id=BOOK))
        await uow.commit()

    async with uow:
        await uow.posts.archive(post.id)
        await uow.rollback()

    assert stub.pages[post.id.value]["in_trash"] is False


async def test_an_exception_in_the_scope_triggers_rollback_automatically(uow, stub):
    with pytest.raises(RuntimeError):
        async with uow:
            await uow.posts.add(make_post(id=None, book_id=BOOK))
            raise RuntimeError("boom")

    assert all(page["in_trash"] for page in stub.pages.values())
