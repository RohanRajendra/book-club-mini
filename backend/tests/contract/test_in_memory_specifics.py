"""Behaviour of the fake that is not part of the port contract.

These are the paths where the fake must be *strict*. A fake that silently
accepts an update to a row that does not exist would let a use-case bug through
and only surface against Notion, which is the worst place to find it.
"""

from __future__ import annotations

import pytest

from app.adapters.memory import InMemoryUnitOfWork
from app.domain.entities import Book
from app.domain.values import BookId, PostId
from tests.builders import at_minute, make_post


@pytest.fixture
def uow():
    return InMemoryUnitOfWork(clock=lambda: at_minute(0))


async def test_updating_an_unknown_book_raises(uow):
    async with uow:
        with pytest.raises(KeyError):
            await uow.books.update(Book(id=BookId("nope"), title="Ghost"))


async def test_updating_an_unknown_post_raises(uow):
    async with uow:
        with pytest.raises(KeyError):
            await uow.posts.update(make_post(id=PostId("nope")))


async def test_archiving_an_unknown_post_raises(uow):
    async with uow:
        with pytest.raises(KeyError):
            await uow.posts.archive(PostId("nope"))


async def test_get_full_body_on_an_unknown_post_raises(uow):
    async with uow:
        with pytest.raises(KeyError):
            await uow.posts.get_full_body(PostId("nope"))


async def test_rollback_outside_a_scope_is_a_no_op(uow):
    """Rolling back twice, or without entering, must not explode — a use case
    that returns Err after an inner rollback would otherwise crash."""
    await uow.rollback()
    async with uow:
        await uow.posts.add(make_post(id=None))
        await uow.rollback()
        await uow.rollback()


async def test_the_clock_is_injected_so_timestamps_are_deterministic(uow):
    async with uow:
        stored = await uow.posts.add(make_post(id=None, created_at=None))
    assert stored.created_at == at_minute(0)


async def test_the_repository_records_its_calls(uow):
    """phase-5 §5.7 asserts on this log rather than reaching for a mock."""
    async with uow:
        stored = await uow.posts.add(make_post(id=None))
        await uow.posts.get(stored.id)
    assert ("get", stored.id.value) in uow.posts.calls


async def test_adding_a_post_with_an_explicit_id_keeps_it(uow):
    """The Notion adapter assigns ids server-side; the fake must not fight a
    caller that already has one."""
    async with uow:
        stored = await uow.posts.add(make_post(id=PostId("chosen")))
    assert stored.id == PostId("chosen")


async def test_two_units_of_work_over_one_store_see_each_others_commits(uow):
    async with uow:
        stored = await uow.posts.add(make_post(id=None))
        await uow.commit()
    async with uow:
        assert await uow.posts.get(stored.id) is not None
