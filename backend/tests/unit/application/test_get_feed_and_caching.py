"""GetFeed and the caching decorator around it."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from app.adapters.memory import InMemoryUnitOfWork
from app.application.caching import CachingFeedQuery
from app.application.feed import FeedAssembler
from app.application.use_cases.get_feed import FeedQuery, GetFeed
from app.domain import errors
from app.domain.entities import Book
from app.domain.policies import ChapterFirstSpoilerPolicy
from app.domain.services import PositionResolver, ScaleCalculator
from app.domain.values import BookId, PostType
from tests.builders import ADA, GRACE, ROSTER, EPOCH, make_post

BOOK = BookId("book-1")


@pytest.fixture
def uow():
    return InMemoryUnitOfWork()


@pytest.fixture
async def seeded(uow):
    async with uow:
        await uow.books.add(Book(id=BOOK, title="Piranesi", total_chapters=30))
        await uow.posts.add(make_post(id=None, book_id=BOOK, member=ADA))
        await uow.commit()
    return uow


@pytest.fixture
def get_feed(seeded):
    return GetFeed(
        uow_factory=lambda: seeded,
        assembler=FeedAssembler(
            ChapterFirstSpoilerPolicy(), PositionResolver(), ScaleCalculator(), ROSTER
        ),
    )


class TestGetFeed:
    async def test_returns_book_positions_and_posts(self, get_feed):
        feed = (await get_feed.execute(FeedQuery(book_id=BOOK, viewer=ADA))).unwrap()
        assert feed.book.title == "Piranesi"
        assert set(feed.positions) == set(ROSTER)
        assert len(feed.posts) == 1

    async def test_unknown_book_returns_book_not_found(self, get_feed):
        result = await get_feed.execute(FeedQuery(book_id=BookId("nope"), viewer=ADA))
        assert isinstance(result.unwrap_err(), errors.BookNotFound)

    async def test_a_feed_load_makes_exactly_one_post_query(self, get_feed, seeded):
        """One data-source query per feed load and no per-post requests — the
        property the rate limit makes load-bearing."""
        seeded.posts.calls.clear()
        await get_feed.execute(FeedQuery(book_id=BOOK, viewer=ADA))

        assert [call[0] for call in seeded.posts.calls] == ["list_for_book"]

    async def test_the_filter_is_passed_through_to_the_assembler(self, get_feed):
        feed = (
            await get_feed.execute(
                FeedQuery(book_id=BOOK, viewer=ADA, post_type=PostType.QUESTION)
            )
        ).unwrap()
        assert feed.posts == []
        assert feed.counts["thought"] == 1


class Clock:
    def __init__(self):
        self.now = EPOCH

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += timedelta(seconds=seconds)


class CountingFeed:
    """Counts calls without a mocking library."""

    def __init__(self, inner: GetFeed):
        self._inner = inner
        self.calls = 0

    async def execute(self, query: FeedQuery):
        self.calls += 1
        return await self._inner.execute(query)


class GatedFeed:
    """A feed query that parks until released.

    The suite's first real interleaving. Everything else here runs to
    completion between statements, which is precisely why a race that needs a
    write to land *during* a read went unnoticed.
    """

    def __init__(self, inner: GetFeed):
        self._inner = inner
        self.calls = 0
        self.gate = asyncio.Event()

    async def execute(self, query: FeedQuery):
        self.calls += 1
        await self.gate.wait()
        return await self._inner.execute(query)


class TestCachingFeedQuery:
    @pytest.fixture
    def clock(self):
        return Clock()

    @pytest.fixture
    def counting(self, get_feed):
        return CountingFeed(get_feed)

    @pytest.fixture
    def cached(self, counting, clock):
        return CachingFeedQuery(counting, clock=clock)

    async def test_second_call_within_the_ttl_does_not_reach_the_inner_use_case(
        self, cached, counting
    ):
        query = FeedQuery(book_id=BOOK, viewer=ADA)
        await cached.execute(query)
        await cached.execute(query)
        assert counting.calls == 1

    async def test_call_after_the_ttl_reaches_the_inner_use_case(
        self, cached, counting, clock
    ):
        query = FeedQuery(book_id=BOOK, viewer=ADA)
        await cached.execute(query)
        clock.advance(21)
        await cached.execute(query)
        assert counting.calls == 2

    async def test_different_books_are_cached_separately(self, cached, counting):
        await cached.execute(FeedQuery(book_id=BOOK, viewer=ADA))
        await cached.execute(FeedQuery(book_id=BookId("other"), viewer=ADA))
        assert counting.calls == 2

    async def test_different_filters_are_cached_separately(self, cached, counting):
        await cached.execute(FeedQuery(book_id=BOOK, viewer=ADA))
        await cached.execute(
            FeedQuery(book_id=BOOK, viewer=ADA, post_type=PostType.QUESTION)
        )
        assert counting.calls == 2

    async def test_the_cache_is_bypassed_for_a_different_viewer(self, cached, counting):
        """Spoiler flags are viewer-specific, so a key without the viewer would
        serve one member's blur state to the other through View as."""
        await cached.execute(FeedQuery(book_id=BOOK, viewer=ADA))
        await cached.execute(FeedQuery(book_id=BOOK, viewer=GRACE))
        assert counting.calls == 2

    async def test_a_write_invalidates_every_cached_entry(self, cached, counting):
        await cached.execute(FeedQuery(book_id=BOOK, viewer=ADA))
        await cached.execute(FeedQuery(book_id=BOOK, viewer=GRACE))
        cached.invalidate()
        await cached.execute(FeedQuery(book_id=BOOK, viewer=ADA))
        await cached.execute(FeedQuery(book_id=BOOK, viewer=GRACE))
        assert counting.calls == 4

    async def test_a_failed_lookup_is_not_cached(self, cached, counting):
        """Caching a BookNotFound would keep a book invisible for 20 seconds
        after it was created."""
        query = FeedQuery(book_id=BookId("nope"), viewer=ADA)
        await cached.execute(query)
        await cached.execute(query)
        assert counting.calls == 2

    async def test_invalidation_is_wired_to_commit_not_to_each_write_site(
        self, cached, counting, seeded
    ):
        """The single invalidation hook: the container registers this on the unit
        of work, so nothing else has to remember to call it."""
        seeded.on_commit.append(cached.invalidate)
        query = FeedQuery(book_id=BOOK, viewer=ADA)

        await cached.execute(query)
        async with seeded:
            await seeded.posts.add(make_post(id=None, book_id=BOOK))
            await seeded.commit()
        await cached.execute(query)

        assert counting.calls == 2


class TestCacheInvalidationDuringAnInFlightRead:
    """A read that began before a write must not repopulate the cache after it.

    `invalidate()` can only clear what is already stored. A read still waiting
    on Notion has nothing in the map to clear, and stores its pre-write
    snapshot the moment it returns — the exact staleness the on_commit hook
    exists to prevent.
    """

    @pytest.fixture
    def gated(self, get_feed):
        return GatedFeed(get_feed)

    @pytest.fixture
    def cached(self, gated, clock):
        return CachingFeedQuery(gated, clock=clock)

    @pytest.fixture
    def clock(self):
        return Clock()

    @staticmethod
    async def _read_across(cached, gated, query):
        """Start a read, let a write commit while it is parked, then release."""
        reader = asyncio.create_task(cached.execute(query))
        await asyncio.sleep(0)
        cached.invalidate()
        gated.gate.set()
        return await reader

    async def test_the_stale_result_is_not_stored(self, cached, gated):
        query = FeedQuery(book_id=BOOK, viewer=ADA)
        await self._read_across(cached, gated, query)

        await cached.execute(query)
        assert gated.calls == 2

    async def test_the_in_flight_reader_still_gets_its_answer(self, cached, gated):
        """Not caching it is not the same as failing it. The member who asked
        gets what was true when they asked."""
        result = await self._read_across(
            cached, gated, FeedQuery(book_id=BOOK, viewer=ADA)
        )
        assert result.unwrap().book.title == "Piranesi"

    async def test_a_slow_read_expires_from_when_it_started_not_when_it_returned(
        self, cached, gated, clock
    ):
        """Freshness is measured from when the data was asked for. A read that
        took fifteen seconds has fifteen seconds less life left — the safe way
        round, since the snapshot is that old by the time it is stored."""
        query = FeedQuery(book_id=BOOK, viewer=ADA)
        reader = asyncio.create_task(cached.execute(query))
        await asyncio.sleep(0)
        clock.advance(15)
        gated.gate.set()
        await reader

        clock.advance(6)
        await cached.execute(query)
        assert gated.calls == 2

    async def test_a_read_started_after_the_write_is_cached_normally(
        self, cached, gated
    ):
        query = FeedQuery(book_id=BOOK, viewer=ADA)
        cached.invalidate()
        gated.gate.set()

        await cached.execute(query)
        await cached.execute(query)
        assert gated.calls == 1


class TestTheCacheIsPerProcess:
    """A known limitation, pinned rather than fixed.

    `CachingFeedQuery` holds its entries in an instance attribute and the
    container builds one per process. Invalidation reaches that instance and
    nothing else, so a second worker — or the other member's machine, running
    its own copy against the same Notion workspace — keeps serving its own
    twenty-second-old view of the feed after a write.

    Fixing it properly means shared state: a cache both processes can reach, or
    a signal between them. Neither belongs in an app two people run for
    themselves, and the failure self-heals in twenty seconds. What matters is
    that it is written down, because "I posted and they cannot see it" is the
    first thing that looks like data loss and is not.
    """

    @pytest.fixture
    def clock(self):
        return Clock()

    async def test_invalidating_one_instance_leaves_another_serving_stale_data(
        self, get_feed, clock
    ):
        first, second = CountingFeed(get_feed), CountingFeed(get_feed)
        mine = CachingFeedQuery(first, clock=clock)
        theirs = CachingFeedQuery(second, clock=clock)
        query = FeedQuery(book_id=BOOK, viewer=ADA)

        await mine.execute(query)
        await theirs.execute(query)
        mine.invalidate()

        await mine.execute(query)
        await theirs.execute(query)

        assert first.calls == 2, "the writer's own process sees its write"
        assert second.calls == 1, "the other process does not"

    async def test_the_other_process_catches_up_when_the_ttl_expires(
        self, get_feed, clock
    ):
        """Which is what keeps this a limitation rather than a defect: it is
        bounded, and the bound is twenty seconds."""
        counting = CountingFeed(get_feed)
        theirs = CachingFeedQuery(counting, clock=clock)
        query = FeedQuery(book_id=BOOK, viewer=ADA)

        await theirs.execute(query)
        clock.advance(21)
        await theirs.execute(query)

        assert counting.calls == 2
