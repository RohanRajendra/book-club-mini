"""HTTP concerns only: status codes, DTO shape, validation, error mapping.

Business assertions belong in the application-layer unit tests.
"""

from __future__ import annotations

import pytest

from tests.api.conftest import BOOK


async def test_health_reports_both_data_source_ids(client, container):
    """On in-memory adapters there are no data source IDs to report; the shape
    is what this asserts. The real IDs are checked live."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert set(response.json()) == {
        "status",
        "books_data_source_id",
        "posts_data_source_id",
    }


async def test_me_returns_the_configured_member_and_roster(client):
    response = await client.get("/api/me")
    assert response.json() == {
        "member": "Ada",
        "members": ["Ada", "Grace"],
        "reader_index": 0,
    }


class TestBooks:
    async def test_list_books_returns_the_seeded_book(self, client):
        response = await client.get("/api/books")
        assert response.status_code == 200
        assert [book["title"] for book in response.json()] == ["Piranesi"]

    async def test_add_book_returns_201(self, client):
        response = await client.post("/api/books", json={"title": "Jonathan Strange"})
        assert response.status_code == 201
        assert response.json()["title"] == "Jonathan Strange"

    async def test_add_book_without_a_title_returns_422(self, client):
        response = await client.post("/api/books", json={})
        assert response.status_code == 422
        assert "error" in response.json()

    async def test_add_book_with_a_blank_title_returns_400(self, client):
        response = await client.post("/api/books", json={"title": "   "})
        assert response.status_code == 400
        assert response.json() == {"error": "A book needs a title."}

    async def test_patch_book_updates_it(self, client):
        response = await client.patch(
            f"/api/books/{BOOK.value}",
            json={"title": "Piranesi", "total_chapters": 45},
        )
        assert response.status_code == 200
        assert response.json()["total_chapters"] == 45

    async def test_patch_of_an_unknown_book_returns_404(self, client):
        response = await client.patch("/api/books/nope", json={"title": "Ghost"})
        assert response.status_code == 404

    async def test_a_zero_chapter_count_is_rejected_by_validation(self, client):
        response = await client.post(
            "/api/books", json={"title": "Piranesi", "total_chapters": 0}
        )
        assert response.status_code == 422


class TestFeed:
    async def test_feed_returns_posts_positions_and_spine(self, client):
        await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 4},
        )
        response = await client.get(f"/api/books/{BOOK.value}/feed")
        body = response.json()

        assert response.status_code == 200
        assert len(body["posts"]) == 1
        assert [entry["member"] for entry in body["positions"]] == ["Ada", "Grace"]
        assert body["spine"] == {"max_chapter": 30, "is_estimated": False}
        assert body["counts"]["progress"] == 1

    async def test_feed_with_an_unknown_book_returns_404(self, client):
        response = await client.get("/api/books/nope/feed")
        assert response.status_code == 404
        assert response.json() == {"error": "That book isn't here."}

    async def test_feed_with_an_unknown_as_member_returns_400(self, client):
        response = await client.get(f"/api/books/{BOOK.value}/feed?as=Alan")
        assert response.status_code == 400
        assert response.json() == {"error": "Alan is not in this club."}

    async def test_feed_as_the_other_member_recomputes_the_flags(self, client):
        await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 40},
        )
        as_ada = await client.get(f"/api/books/{BOOK.value}/feed?as=Ada")
        as_grace = await client.get(f"/api/books/{BOOK.value}/feed?as=Grace")

        assert as_ada.json()["posts"][0]["is_own"] is True
        assert as_grace.json()["posts"][0]["is_own"] is False

    async def test_post_response_never_includes_the_full_body(self, client):
        await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "x" * 4000},
        )
        response = await client.get(f"/api/books/{BOOK.value}/feed")
        post = response.json()["posts"][0]

        assert "body" not in post
        assert post["has_full_body"] is True
        assert len(post["body_preview"]) <= 1900

    async def test_feed_response_includes_a_position_entry_for_every_roster_member(
        self, client
    ):
        response = await client.get(f"/api/books/{BOOK.value}/feed")
        positions = response.json()["positions"]
        assert [entry["member"] for entry in positions] == ["Ada", "Grace"]
        assert all(entry["position"] is None for entry in positions)


class TestPosts:
    async def test_create_post_returns_201_with_the_created_post(self, client):
        response = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "The statues."},
        )
        assert response.status_code == 201
        assert response.json()["body_preview"] == "The statues."
        assert response.json()["is_own"] is True

    async def test_create_progress_without_a_chapter_returns_400_with_a_readable_message(
        self, client
    ):
        response = await client.post(
            "/api/posts", json={"book_id": BOOK.value, "type": "Progress"}
        )
        assert response.status_code == 400
        assert response.json() == {"error": "Progress needs a chapter number."}

    async def test_create_post_for_an_unknown_book_returns_404(self, client):
        response = await client.post(
            "/api/posts", json={"book_id": "nope", "type": "Thought", "body": "x"}
        )
        assert response.status_code == 404

    async def test_a_post_is_attributed_to_this_installation_not_the_request(
        self, client
    ):
        """The request body cannot set the author. There is no auth, but there
        is also no way to ask for someone else's name."""
        response = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Thought",
                "body": "x",
                "member": "Grace",
            },
        )
        assert response.json()["member"] == "Ada"

    async def test_edit_another_members_post_returns_403(self, client, uow_factory):
        from app.domain.values import MemberName
        from tests.builders import GRACE, make_post

        uow = uow_factory()
        async with uow:
            hers = await uow.posts.add(make_post(id=None, book_id=BOOK, member=GRACE))
            await uow.commit()

        response = await client.patch(
            f"/api/posts/{hers.id.value}", json={"body": "Mine now.", "chapter": 9}
        )
        assert response.status_code == 403
        assert response.json() == {"error": "You can only edit your own posts."}

    async def test_edit_returns_the_updated_post(self, client):
        created = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "First."},
        )
        response = await client.patch(
            f"/api/posts/{created.json()['id']}",
            json={"body": "Second.", "chapter": 9},
        )
        assert response.status_code == 200
        assert response.json()["body_preview"] == "Second."

    async def test_delete_returns_204(self, client):
        created = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Bye."},
        )
        response = await client.delete(f"/api/posts/{created.json()['id']}")
        assert response.status_code == 204
        assert response.content == b""

    async def test_delete_of_an_unknown_post_returns_404(self, client):
        assert (await client.delete("/api/posts/nope")).status_code == 404

    async def test_body_endpoint_returns_the_full_text(self, client):
        body = "The house is the world. " * 200
        created = await client.post(
            "/api/posts", json={"book_id": BOOK.value, "type": "Thought", "body": body}
        )
        response = await client.get(f"/api/posts/{created.json()['id']}/body")
        assert response.status_code == 200
        assert response.json() == {"body": body}

    async def test_body_endpoint_on_an_unknown_post_returns_404(self, client):
        assert (await client.get("/api/posts/nope/body")).status_code == 404

    async def test_a_reply_is_nested_under_its_parent_in_the_feed(self, client):
        parent = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Parent.", "chapter": 9},
        )
        await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Thought",
                "body": "Reply.",
                "parent_post_id": parent.json()["id"],
            },
        )
        feed = await client.get(f"/api/books/{BOOK.value}/feed")
        posts = feed.json()["posts"]

        assert len(posts) == 1
        assert posts[0]["replies"][0]["type"] == "Reply"
        assert posts[0]["replies"][0]["position"] == {"chapter": 9, "page": None}

    async def test_replying_to_a_reply_returns_400(self, client):
        parent = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Parent."},
        )
        reply = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Thought",
                "body": "Reply.",
                "parent_post_id": parent.json()["id"],
            },
        )
        response = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Thought",
                "body": "Nested.",
                "parent_post_id": reply.json()["id"],
            },
        )
        assert response.status_code == 400
        assert response.json() == {"error": "Replies are one level deep."}


class TestErrorShape:
    async def test_malformed_json_returns_422_not_500(self, client):
        response = await client.post(
            "/api/posts",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "error" in response.json()

    async def test_error_response_shape_is_a_single_error_string(self, client):
        response = await client.get("/api/books/nope/feed")
        assert list(response.json()) == ["error"]
        assert isinstance(response.json()["error"], str)

    async def test_notion_api_error_becomes_502_without_leaking_the_body(
        self, client, container
    ):
        from app.adapters.notion.http import NotionApiError

        async def explode():
            raise NotionApiError(403, "restricted_resource", "Integration lacks access")

        original = container.list_books
        container.list_books = lambda: type("X", (), {"execute": staticmethod(explode)})()
        try:
            response = await client.get("/api/books")
        finally:
            container.list_books = original

        assert response.status_code == 502
        assert response.json() == {"error": "Can't reach Notion right now. Try refreshing."}
        assert "restricted_resource" not in response.text

    async def test_unhandled_exception_becomes_500_without_a_traceback(
        self, client, container
    ):
        async def explode():
            raise RuntimeError("kaboom in the internals")

        original = container.list_books
        container.list_books = lambda: type("X", (), {"execute": staticmethod(explode)})()
        try:
            response = await client.get("/api/books")
        finally:
            container.list_books = original

        assert response.status_code == 500
        assert "kaboom" not in response.text
        assert "Traceback" not in response.text


class TestCaching:
    async def test_two_feed_requests_within_the_ttl_cost_one_query(
        self, client, uow_factory
    ):
        uow = uow_factory()
        await client.get(f"/api/books/{BOOK.value}/feed")
        uow.posts.calls.clear()
        await client.get(f"/api/books/{BOOK.value}/feed")

        assert uow.posts.calls == []

    async def test_two_feed_requests_with_different_as_values_are_cached_separately(
        self, client, uow_factory
    ):
        await client.get(f"/api/books/{BOOK.value}/feed?as=Ada")
        uow = uow_factory()
        uow.posts.calls.clear()
        await client.get(f"/api/books/{BOOK.value}/feed?as=Grace")

        assert [call[0] for call in uow.posts.calls] == ["list_for_book"]

    async def test_posting_invalidates_the_feed_cache(self, client):
        """The first bug the owner would hit, and would report as "the app
        doesn't work"."""
        await client.get(f"/api/books/{BOOK.value}/feed")
        await client.post(
            "/api/posts", json={"book_id": BOOK.value, "type": "Thought", "body": "New."}
        )
        feed = await client.get(f"/api/books/{BOOK.value}/feed")

        assert len(feed.json()["posts"]) == 1

    async def test_a_feed_request_makes_exactly_one_post_query(
        self, client, uow_factory
    ):
        uow = uow_factory()
        uow.posts.calls.clear()
        await client.get(f"/api/books/{BOOK.value}/feed")

        assert [call[0] for call in uow.posts.calls] == ["list_for_book"]
