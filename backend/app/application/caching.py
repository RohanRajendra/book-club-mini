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

    async def execute(self, query: FeedQuery) -> Result[Feed]:
        # The viewer is part of the key because spoiler flags are computed per
        # viewer; without it the View as control serves one member's blur state
        # to the other.
        key = (query.book_id, query.viewer, query.post_type)
        now = self._clock()

        cached = self._entries.get(key)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]

        result = await self._inner.execute(query)
        if result.is_ok():
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
        self._entries.clear()
