"""database_id → data_source_id.

Since API version 2025-09-03 a database is a container holding one or more data
sources, and rows live on the data source. The ID in a Notion URL is the
*database* ID; the two are not interchangeable, and sending one where the other
belongs is this API's signature mistake.

Resolved once at startup by the container, not per request.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DataSourceResolver:
    def __init__(self, client) -> None:
        self._client = client
        self._cache: dict[str, str] = {}

    async def resolve(self, database_id: str) -> str:
        if database_id in self._cache:
            return self._cache[database_id]

        database = await self._client.get(f"/databases/{database_id}")
        sources = database.get("data_sources") or []

        if not sources:
            raise ValueError(
                f"Notion database {database_id} has no data sources. Recreate it "
                "in the Notion UI, or check that the ID is a database ID and not "
                "a page ID."
            )
        if len(sources) > 1:
            # A second data source means the owner added one in Notion, which
            # this app does not support.
            logger.warning(
                "database %s has %d data sources; using the first",
                database_id,
                len(sources),
            )

        self._cache[database_id] = sources[0]["id"]
        return self._cache[database_id]
