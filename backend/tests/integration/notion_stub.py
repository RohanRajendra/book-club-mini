"""A small stateful Notion, backed by respx.

Pages in a dict, queries filtering over them, trashed flags respected. It is
what lets the shared contract suite run against the Notion adapter without the
network.

This proves conformance to *our model* of Notion, not to Notion itself. Running
the adapter against a real workspace is what closes that gap, and it is not
optional before trusting a change to this layer.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import Any

import httpx

from app.adapters.notion.http import BASE_URL

BOOKS_DS = "books-data-source"
POSTS_DS = "posts-data-source"
BOOKS_DB = "books-database"
POSTS_DB = "posts-database"


class NotionStub:
    def __init__(self) -> None:
        self.pages: dict[str, dict[str, Any]] = {}
        self.blocks: dict[str, list[dict[str, Any]]] = {}
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self._ids = count(1)
        self._now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        self._clock_step = timedelta(seconds=1)
        #: Set to a status code to make the next matching write fail.
        self.fail_next: dict[str, int] = {}

    # ------------------------------------------------------------- helpers

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    def hold_clock(self) -> None:
        """Stop the clock, so everything created next shares a timestamp.

        Real Notion truncates `created_time` to the minute — every page in a
        live workspace reports `:00.000Z` — so pages created moments apart tie
        as a matter of course. The stub ticks per write for the tests that need
        distinct timestamps; this is how a test asks for the other case.
        """
        self._clock_step = timedelta(0)

    def _tick(self) -> str:
        self._now += self._clock_step
        return self._now.isoformat().replace("+00:00", "Z")

    def _maybe_fail(self, key: str) -> httpx.Response | None:
        status = self.fail_next.pop(key, None)
        if status is None:
            return None
        return httpx.Response(
            status, json={"code": "validation_error", "message": f"stub failure: {key}"}
        )

    # -------------------------------------------------------------- routes

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.replace("/v1", "", 1)
        payload = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, payload))

        for pattern, method, handle in self._routes():
            if request.method != method:
                continue
            match = re.fullmatch(pattern, path)
            if match:
                return handle(match, payload, request)

        return httpx.Response(
            404, json={"code": "object_not_found", "message": f"no route {path}"}
        )

    def _routes(self):
        return [
            (r"/databases/(?P<id>[^/]+)", "GET", self._get_database),
            (r"/data_sources/(?P<id>[^/]+)/query", "POST", self._query),
            (r"/pages", "POST", self._create_page),
            (r"/pages/(?P<id>[^/]+)", "GET", self._get_page),
            (r"/pages/(?P<id>[^/]+)", "PATCH", self._patch_page),
            (r"/blocks/(?P<id>[^/]+)/children", "GET", self._get_children),
            (r"/blocks/(?P<id>[^/]+)/children", "PATCH", self._append_children),
            (r"/blocks/(?P<id>[^/]+)", "PATCH", self._patch_block),
            (r"/blocks/(?P<id>[^/]+)", "DELETE", self._delete_block),
        ]

    # ------------------------------------------------------------ handlers

    def _get_database(self, match, payload, request):
        database_id = match.group("id")
        data_source = BOOKS_DS if database_id == BOOKS_DB else POSTS_DS
        return httpx.Response(
            200,
            json={
                "object": "database",
                "id": database_id,
                "title": [{"plain_text": "Books"}],
                "data_sources": [{"id": data_source, "name": "Default"}],
            },
        )

    def _query(self, match, payload, request):
        payload = payload or {}
        rows = [
            page
            for page in self.pages.values()
            if page["_data_source"] == match.group("id")
            # Notion excludes trashed pages from query results by default.
            and not page["in_trash"]
            and _matches(page, payload.get("filter"))
        ]

        # Creation order, for breaking a tie. Measured against a live
        # workspace: under a descending created_time sort Notion returns a
        # tied pair newest first — a reply, which cannot predate its parent,
        # comes back before it.
        created_order = {page_id: index for index, page_id in enumerate(self.pages)}
        for sort in reversed(payload.get("sorts") or []):
            if sort.get("timestamp") == "created_time":
                rows.sort(
                    key=lambda page: (page["created_time"], created_order[page["id"]]),
                    reverse=sort.get("direction") == "descending",
                )

        size = payload.get("page_size", 100)
        start = int(payload.get("start_cursor") or 0)
        window = rows[start : start + size]
        has_more = start + size < len(rows)

        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [_public(page) for page in window],
                "has_more": has_more,
                "next_cursor": str(start + size) if has_more else None,
            },
        )

    def _create_page(self, match, payload, request):
        failure = self._maybe_fail("create_page")
        if failure:
            return failure

        parent = payload["parent"]
        if parent.get("type") != "data_source_id":
            return httpx.Response(
                400,
                json={
                    "code": "validation_error",
                    "message": "parent.type must be data_source_id",
                },
            )

        now = self._tick()
        page_id = self._next_id("page")
        self.pages[page_id] = {
            "id": page_id,
            "object": "page",
            "_data_source": parent["data_source_id"],
            "created_time": now,
            "last_edited_time": now,
            "in_trash": False,
            "properties": payload.get("properties", {}),
        }
        self.blocks[page_id] = []
        return httpx.Response(200, json=_public(self.pages[page_id]))

    def _get_page(self, match, payload, request):
        page = self.pages.get(match.group("id"))
        if page is None:
            return httpx.Response(
                404, json={"code": "object_not_found", "message": "page not found"}
            )
        return httpx.Response(200, json=_public(page))

    def _patch_page(self, match, payload, request):
        failure = self._maybe_fail("patch_page")
        if failure:
            return failure

        page = self.pages.get(match.group("id"))
        if page is None:
            return httpx.Response(
                404, json={"code": "object_not_found", "message": "page not found"}
            )

        if "properties" in payload:
            page["properties"] = {**page["properties"], **payload["properties"]}
        if "in_trash" in payload:
            page["in_trash"] = payload["in_trash"]
        if "archived" in payload:
            page["in_trash"] = payload["archived"]
        page["last_edited_time"] = self._tick()
        return httpx.Response(200, json=_public(page))

    def _get_children(self, match, payload, request):
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": self.blocks.get(match.group("id"), []),
                "has_more": False,
                "next_cursor": None,
            },
        )

    def _append_children(self, match, payload, request):
        failure = self._maybe_fail("append_block")
        if failure:
            return failure

        page_id = match.group("id")
        created = []
        for child in payload["children"]:
            block = {**child, "id": self._next_id("block"), "object": "block"}
            self.blocks.setdefault(page_id, []).append(block)
            created.append(block)
        return httpx.Response(200, json={"object": "list", "results": created})

    def _patch_block(self, match, payload, request):
        failure = self._maybe_fail("patch_block")
        if failure:
            return failure

        block_id = match.group("id")
        for blocks in self.blocks.values():
            for block in blocks:
                if block["id"] == block_id:
                    block.update(payload)
                    return httpx.Response(200, json=block)
        return httpx.Response(
            404, json={"code": "object_not_found", "message": "block not found"}
        )

    def _delete_block(self, match, payload, request):
        block_id = match.group("id")
        for page_id, blocks in self.blocks.items():
            for block in list(blocks):
                if block["id"] == block_id:
                    blocks.remove(block)
                    return httpx.Response(200, json={"id": block_id, "archived": True})
        return httpx.Response(
            404, json={"code": "object_not_found", "message": "block not found"}
        )

    # ------------------------------------------------------------ querying

    def paths(self, method: str | None = None) -> list[str]:
        return [
            path
            for verb, path, _ in self.requests
            if method is None or verb == method
        ]


def _public(page: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in page.items() if not key.startswith("_")}


def _matches(page: dict[str, Any], filter_: dict[str, Any] | None) -> bool:
    if not filter_:
        return True
    prop = page["properties"].get(filter_["property"], {})
    if "relation" in filter_:
        wanted = filter_["relation"]["contains"]
        return any(item["id"] == wanted for item in prop.get("relation", []))
    return True  # pragma: no cover - only the relation filter is used


def mount(respx_mock, stub: NotionStub) -> NotionStub:
    respx_mock.route(url__startswith=BASE_URL).mock(side_effect=stub.handler)
    return stub
