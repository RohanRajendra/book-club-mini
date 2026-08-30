"""The one place this app talks to Notion.

Every Notion call goes through `NotionHttpClient`, which owns the process's
single `httpx.AsyncClient`, the rate limiter, and the retry policy. Notion's
limit is roughly 3 requests/second per integration and it is the app's real
ceiling, so there is exactly one place to enforce it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

NOTION_VERSION = "2025-09-03"
BASE_URL = "https://api.notion.com/v1"
TIMEOUT = 30.0

#: Aim below the ceiling deliberately: Notion's ~3/sec is an average, bursts
#: are what trigger the 429s, and this app has two users and no throughput
#: pressure.
BUCKET_CAPACITY = 3
REFILL_PER_SECOND = 2.5

MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0


class NotionApiError(Exception):
    """Infrastructure failure, not a DomainError.

    Becomes a 502 in the interface layer. A raw Notion error body must never
    reach the browser.
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"Notion {status} {code}: {message}")
        self.status = status
        self.code = code
        self.notion_message = message


class TokenBucket:
    """Serialises outbound requests below Notion's ceiling.

    Guarded by an asyncio.Lock so two concurrent handlers cannot both drain it.
    """

    def __init__(
        self,
        capacity: int = BUCKET_CAPACITY,
        refill_per_second: float = REFILL_PER_SECOND,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._tokens = float(capacity)
        self._updated = self._clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            self._tokens = min(
                self._capacity, self._tokens + (now - self._updated) * self._refill
            )
            self._updated = now

            if self._tokens < 1:
                wait = (1 - self._tokens) / self._refill
                await self._sleep(wait)
                self._tokens = 0.0
                self._updated = self._clock()
            else:
                self._tokens -= 1


class NotionHttpClient:
    def __init__(
        self,
        token: str,
        client: httpx.AsyncClient | None = None,
        bucket: TokenBucket | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        self._bucket = bucket or TokenBucket()
        self._sleep = sleep or asyncio.sleep

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, payload)

    async def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", path, payload)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        last: httpx.Response | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._bucket.acquire()

            started = time.monotonic()
            response = await self._client.request(
                method, url, json=payload, headers=self._headers
            )
            elapsed = time.monotonic() - started
            # The only instrumentation worth having: when the app feels slow
            # the question is always "how many Notion calls did that cost".
            logger.info("notion %s %s -> %s in %.0fms", method, path, response.status_code, elapsed * 1000)

            if response.status_code < 400:
                return response.json() if response.content else {}

            last = response
            if not self._should_retry(response.status_code) or attempt == MAX_ATTEMPTS:
                break
            await self._sleep(self._backoff(response, attempt))

        raise self._error(last)

    @staticmethod
    def _should_retry(status: int) -> bool:
        # Retrying a 400 just delays the error.
        return status == 429 or status >= 500

    @staticmethod
    def _backoff(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if response.status_code == 429 and retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return BACKOFF_BASE * (2 ** (attempt - 1))

    @staticmethod
    def _error(response: httpx.Response | None) -> NotionApiError:
        if response is None:  # pragma: no cover - loop always assigns
            return NotionApiError(0, "unknown", "no response")
        try:
            body = response.json()
        except ValueError:
            body = {}
        return NotionApiError(
            response.status_code,
            body.get("code", "unknown"),
            body.get("message", response.text[:200]),
        )
