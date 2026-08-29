"""The contract every port implementation must satisfy.

This is the Liskov check for the whole port design, and it is what makes the
in-memory adapter trustworthy as a test double for every later test. Phase 4
adds a Notion subclass and **must not modify this suite**: if a contract test
cannot pass, either the adapter is wrong or the port is.

A future SQLite adapter is correct when this suite passes against it. That is
the concrete meaning of the swappability goal.
"""

from __future__ import annotations

import pytest

from app.adapters.memory import InMemoryUnitOfWork, in_memory_uow_factory
from app.domain.entities import Book, Post
from app.domain.values import BookId, BookStatus, PostId, PostType
from tests.builders import ADA, GRACE, long_body, make_book, make_post, make_reply

NO_TRANSACTIONS = (
    "Notion has no transactions; rollback is compensating and is covered by "
    "the compensation tests in Phase 4."
)


class UnitOfWorkContract:
    """Subclass this once per implementation and supply the two fixtures."""

    #: False for implementations whose rollback is compensating rather than
    #: atomic. The conftest hook skips fake_only tests for those.
    supports_transactions = True

    @pytest.fixture
    def uow(self):
        raise NotImplementedError

    @pytest.fixture
    def uow_factory(self):
        raise NotImplementedError

    # ---------------------------------------------------------------- books

    async def test_added_book_is_retrievable_by_id(self, uow):
        async with uow:
            stored = await uow.books.add(Book(title="Piranesi"))
            assert await uow.books.get(stored.id) == stored

    async def test_added_book_appears_in_list_all(self, uow):
        async with uow:
            stored = await uow.books.add(Book(title="Piranesi"))
            assert [book.id for book in await uow.books.list_all()] == [stored.id]

    async def test_get_returns_none_for_unknown_book_id(self, uow):
        async with uow:
            assert await uow.books.get(BookId("nope")) is None

    async def test_updated_book_reflects_new_values(self, uow):
        async with uow:
            stored = await uow.books.add(Book(title="Piranesi"))
            updated = await uow.books.update(
                Book(
                    id=stored.id,
                    title="Piranesi",
                    author="Susanna Clarke",
                    status=BookStatus.CURRENTLY_READING,
                    total_chapters=30,
                )
            )
            assert updated.author == "Susanna Clarke"
            assert updated.total_chapters == 30
            assert (await uow.books.get(stored.id)).status is BookStatus.CURRENTLY_READING

    async def test_list_all_returns_books_from_an_empty_store_as_empty_list(self, uow):
        async with uow:
            assert await uow.books.list_all() == []

    # ---------------------------------------------------------------- posts

    async def test_added_post_is_retrievable_by_id(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None))
            assert (await uow.posts.get(stored.id)).body_preview == stored.body_preview

    async def test_add_returns_a_post_with_an_id_and_created_at(self, uow):
        """An unsaved post carries neither (docs/spec-deltas.md D9)."""
        async with uow:
            stored = await uow.posts.add(make_post(id=None, created_at=None))
            assert stored.id is not None
            assert stored.created_at is not None

    async def test_posts_are_listed_only_for_their_own_book(self, uow):
        async with uow:
            mine = await uow.posts.add(make_post(id=None, book_id=BookId("book-1")))
            await uow.posts.add(make_post(id=None, book_id=BookId("book-2")))
            listed = await uow.posts.list_for_book(BookId("book-1"))
            assert [post.id for post in listed] == [mine.id]

    async def test_archived_post_is_not_listed(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None))
            await uow.posts.archive(stored.id)
            assert await uow.posts.list_for_book(stored.book_id) == []

    async def test_archived_post_is_still_retrievable_by_id(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None))
            await uow.posts.archive(stored.id)
            assert await uow.posts.get(stored.id) is not None

    async def test_reply_is_listed_alongside_top_level_posts(self, uow):
        async with uow:
            parent = await uow.posts.add(make_post(id=None))
            reply = await uow.posts.add(make_reply(parent, GRACE, id=None))
            listed = await uow.posts.list_for_book(parent.book_id)
            assert {post.id for post in listed} == {parent.id, reply.id}

    async def test_short_post_reports_has_full_body_false(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None, body_preview="Short."))
            assert (await uow.posts.get(stored.id)).has_full_body is False

    async def test_long_post_reports_has_full_body_true(self, uow):
        body = long_body()
        async with uow:
            stored = await uow.posts.add(
                make_post(id=None, body_preview=body[:1900], has_full_body=True), body
            )
            assert (await uow.posts.get(stored.id)).has_full_body is True

    async def test_full_body_round_trips_above_1900_characters(self, uow):
        body = long_body(5000)
        async with uow:
            stored = await uow.posts.add(
                make_post(id=None, body_preview=body[:1900], has_full_body=True), body
            )
            assert await uow.posts.get_full_body(stored.id) == body

    async def test_get_full_body_on_a_short_post_returns_the_preview(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None, body_preview="Short."))
            assert await uow.posts.get_full_body(stored.id) == "Short."

    async def test_updating_a_post_from_long_to_short_removes_the_full_body(self, uow):
        body = long_body()
        async with uow:
            stored = await uow.posts.add(
                make_post(id=None, body_preview=body[:1900], has_full_body=True), body
            )
            await uow.posts.update(
                Post(
                    id=stored.id,
                    book_id=stored.book_id,
                    member=stored.member,
                    type=stored.type,
                    body_preview="Now short.",
                    has_full_body=False,
                    position=stored.position,
                    created_at=stored.created_at,
                ),
                None,
            )
            assert await uow.posts.get_full_body(stored.id) == "Now short."

    async def test_updating_a_post_from_short_to_long_stores_a_full_body(self, uow):
        body = long_body()
        async with uow:
            stored = await uow.posts.add(make_post(id=None, body_preview="Short."))
            await uow.posts.update(
                Post(
                    id=stored.id,
                    book_id=stored.book_id,
                    member=stored.member,
                    type=stored.type,
                    body_preview=body[:1900],
                    has_full_body=True,
                    position=stored.position,
                    created_at=stored.created_at,
                ),
                body,
            )
            assert await uow.posts.get_full_body(stored.id) == body

    async def test_updating_a_long_post_replaces_rather_than_appends_the_full_body(
        self, uow
    ):
        first, second = long_body(4000), long_body(3000).replace("house", "labyrinth")
        async with uow:
            stored = await uow.posts.add(
                make_post(id=None, body_preview=first[:1900], has_full_body=True), first
            )
            await uow.posts.update(
                Post(
                    id=stored.id,
                    book_id=stored.book_id,
                    member=stored.member,
                    type=stored.type,
                    body_preview=second[:1900],
                    has_full_body=True,
                    position=stored.position,
                    created_at=stored.created_at,
                ),
                second,
            )
            assert await uow.posts.get_full_body(stored.id) == second

    # ------------------------------------------------------- transactional

    @pytest.mark.fake_only(reason=NO_TRANSACTIONS)
    async def test_rollback_discards_an_added_post(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None))
            await uow.rollback()
            assert await uow.posts.get(stored.id) is None

    @pytest.mark.fake_only(reason=NO_TRANSACTIONS)
    async def test_rollback_discards_an_update(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None, body_preview="Original."))
            await uow.commit()

        async with uow:
            await uow.posts.update(
                Post(
                    id=stored.id,
                    book_id=stored.book_id,
                    member=stored.member,
                    type=stored.type,
                    body_preview="Changed.",
                    position=stored.position,
                    created_at=stored.created_at,
                )
            )
            await uow.rollback()
            assert (await uow.posts.get(stored.id)).body_preview == "Original."

    @pytest.mark.fake_only(reason=NO_TRANSACTIONS)
    async def test_rollback_restores_an_archived_post(self, uow):
        async with uow:
            stored = await uow.posts.add(make_post(id=None))
            await uow.commit()

        async with uow:
            await uow.posts.archive(stored.id)
            await uow.rollback()
            assert await uow.posts.list_for_book(stored.book_id) != []

    async def test_commit_persists_across_a_new_unit_of_work(self, uow_factory):
        first = uow_factory()
        async with first:
            stored = await first.posts.add(make_post(id=None))
            await first.commit()

        second = uow_factory()
        async with second:
            assert await second.posts.get(stored.id) is not None

    async def test_on_commit_callbacks_run_after_a_successful_commit(self, uow):
        """The single invalidation hook (docs/spec-deltas.md D7)."""
        fired = []
        uow.on_commit.append(lambda: fired.append(True))
        async with uow:
            await uow.posts.add(make_post(id=None))
            assert fired == []
            await uow.commit()
        assert fired == [True]

    async def test_on_commit_callbacks_do_not_run_after_a_rollback(self, uow):
        fired = []
        uow.on_commit.append(lambda: fired.append(True))
        async with uow:
            await uow.posts.add(make_post(id=None))
            await uow.rollback()
        assert fired == []

    async def test_an_exception_inside_the_scope_rolls_back(self, uow):
        fired = []
        uow.on_commit.append(lambda: fired.append(True))
        with pytest.raises(RuntimeError):
            async with uow:
                await uow.posts.add(make_post(id=None))
                raise RuntimeError("boom")
        assert fired == []


class TestInMemoryUnitOfWork(UnitOfWorkContract):
    supports_transactions = True

    @pytest.fixture
    def uow(self):
        return InMemoryUnitOfWork()

    @pytest.fixture
    def uow_factory(self):
        return in_memory_uow_factory()
