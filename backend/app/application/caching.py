"""A caching decorator over the feed query.

Caching is orthogonal to feed assembly, so it wraps rather than complicates
`GetFeed`, and every assembler test runs without cache interference.

Twenty seconds is tuned to the refresh model: the frontend refreshes on window
focus, so a member alt-tabbing back repeatedly must not fire a Notion query
each time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from app.application.dto import Feed
from app.application.use_cases.get_feed import FeedQuery, GetFeed
from app.domain.result import Result

TTL = timedelta(seconds=20)


class CachingFeedQuery:
    """Implements the same interface as `GetFeed` and wraps an instance of it."""

    def __init__(
        self,
        inner: GetFeed,
        clock: Callable[[], datetime] | None = None,
        ttl: timedelta = TTL,
    ) -> None:
        self._inner = inner
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ttl = ttl
        self._entries: dict[tuple, tuple[datetime, Result[Feed]]] = {}
        #: Bumped by every invalidation. A read carries the value it started
        #: with, which is the only way to tell that a write landed while it was
        #: in flight — clearing the map cannot reach a result not yet in it.
        self._generation = 0

    async def execute(self, query: FeedQuery) -> Result[Feed]:
        # The viewer is part of the key because spoiler flags are computed per
        # viewer; without it the View as control serves one member's blur state
        # to the other.
        key = (query.book_id, query.viewer, query.post_type)
        # Sampled before the query and used to stamp the entry after it, so
        # freshness is measured from when the data was asked for rather than
        # when it arrived. A slow read expires sooner, which is the safe way
        # round.
        now = self._clock()
        generation = self._generation

        cached = self._entries.get(key)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]

        result = await self._inner.execute(query)
        # The caller still gets this answer — it was true when they asked. What
        # it must not do is become everyone else's answer for the next twenty
        # seconds, which is what storing a snapshot the write already
        # superseded would mean.
        if result.is_ok() and self._generation == generation:
            self._entries[key] = (now, result)
        return result

    def invalidate(self) -> None:
        """Any write clears everything.

        The dataset is tiny and selective invalidation is not worth the bug
        surface. This is registered on the unit of work's `on_commit`, so it
        happens in exactly one place rather than at each write site — a stale
        feed after posting is the first bug the owner would hit, and would
        report as "the app doesn't work".
        """
        self._generation += 1
        self._entries.clear()
