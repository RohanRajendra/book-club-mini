"""HTTP concerns only: status codes, DTO shape, validation, error mapping.

Business assertions belong in the application-layer unit tests.
"""

from __future__ import annotations

import pytest

from app.domain.values import Position, PostType
from app.composition import Container
from tests.api.conftest import BOOK, PASSPHRASE, sign_in_as
from tests.builders import ADA, GRACE, make_post


async def test_health_says_only_that_the_app_is_up(client):
    """It used to report both Notion data source IDs — a useful debugging aid
    on localhost, and an unauthenticated disclosure of workspace structure the
    moment the app has a public URL."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestSigningIn:
    """One shared secret keeps strangers out; the name is a choice.

    Every refusal says the same sentence. Telling a caller that the passphrase
    was right but the name was wrong hands them half the answer.
    """

    async def test_the_right_passphrase_returns_a_session(self, shared_client):
        response = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "Grace"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "member": "Grace",
            "members": ["Ada", "Grace"],
            "reader_index": 1,
            "signed_in": True,
        }

    async def test_the_cookie_it_sets_actually_works(self, shared_client):
        await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "Grace"}
        )
        assert (await shared_client.get("/api/me")).json()["member"] == "Grace"

    async def test_the_cookie_is_not_readable_by_scripts(self, shared_client):
        """The app never reads it from JavaScript, so a stolen XSS payload
        should not be able to either."""
        response = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "Ada"}
        )
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "secure" in cookie

    async def test_the_wrong_passphrase_is_refused(self, shared_client):
        response = await shared_client.post(
            "/api/session", json={"passphrase": "guess", "member": "Ada"}
        )
        assert response.status_code == 401
        assert (await shared_client.get("/api/me")).status_code == 401

    async def test_a_name_outside_the_roster_is_refused(self, shared_client):
        response = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "Mallory"}
        )
        assert response.status_code == 401

    async def test_both_refusals_say_the_same_thing(self, shared_client):
        """Different wording would say which half was wrong."""
        wrong_secret = await shared_client.post(
            "/api/session", json={"passphrase": "guess", "member": "Ada"}
        )
        wrong_name = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "Mallory"}
        )
        assert wrong_secret.json() == wrong_name.json()

    async def test_a_blank_name_is_rejected_by_the_schema(self, shared_client):
        response = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "   "}
        )
        assert response.status_code == 422

    async def test_the_name_may_be_spelled_in_any_case(self, shared_client):
        response = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "grace"}
        )
        assert response.status_code == 200

    async def test_the_roster_spelling_wins_over_what_was_typed(
        self, shared_client
    ):
        """Whatever is typed here becomes the Member value written into Notion
        and the name rendered back. It should not depend on the shift key."""
        response = await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "gRaCe"}
        )
        assert response.json()["member"] == "Grace"
        assert (await shared_client.get("/api/me")).json()["member"] == "Grace"

    async def test_a_post_carries_the_roster_spelling(self, shared_client):
        await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "grace"}
        )
        created = await shared_client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Hers."},
        )
        assert created.json()["member"] == "Grace"

    async def test_signing_out_revokes_the_session(self, shared_client):
        await shared_client.post(
            "/api/session", json={"passphrase": PASSPHRASE, "member": "Ada"}
        )
        assert (await shared_client.delete("/api/session")).status_code == 204
        assert (await shared_client.get("/api/me")).status_code == 401

    async def test_signing_out_when_not_signed_in_is_not_an_error(
        self, shared_client
    ):
        """Reporting one would tell a caller whether their cookie was valid."""
        assert (await shared_client.delete("/api/session")).status_code == 204

    async def test_an_installation_with_no_secrets_has_no_sign_in(self, client):
        """`open` mode with nothing configured. The route exists in the code
        but there is nothing for it to verify against."""
        response = await client.post(
            "/api/session", json={"passphrase": "anything", "member": "Ada"}
        )
        assert response.status_code == 404


class TestIdentityComesFromTheSession:
    """Identity used to be one configuration value, `container.member`.

    That is correct for a process on one person's machine and wrong the moment
    two people share a deployment: both would be the same person, and every
    post either of them wrote would be attributed to whoever the server was
    configured as.
    """

    async def test_without_a_session_everything_is_refused(self, shared_client):
        for method, path in (
            ("GET", "/api/me"),
            ("GET", "/api/books"),
            ("GET", f"/api/books/{BOOK.value}/feed"),
            ("POST", "/api/posts"),
            ("PATCH", "/api/posts/whatever"),
            ("DELETE", "/api/posts/whatever"),
            ("GET", "/api/posts/whatever/body"),
        ):
            response = await shared_client.request(method, path, json={})
            assert response.status_code == 401, f"{method} {path}"

    async def test_health_stays_open(self, shared_client):
        """A deployment platform has to be able to ask whether the app is up
        without holding a passphrase."""
        assert (await shared_client.get("/api/health")).status_code == 200

    async def test_a_session_says_who_you_are(self, shared_client):
        sign_in_as(shared_client, "Grace")
        assert (await shared_client.get("/api/me")).json() == {
            "member": "Grace",
            "members": ["Ada", "Grace"],
            "reader_index": 1,
            "signed_in": True,
        }

    async def test_the_colour_follows_the_session_not_the_server(self, shared_client):
        """`reader_index` selects a colour. Read from configuration it would be
        the same for both members of a shared deployment."""
        sign_in_as(shared_client, "Ada")
        assert (await shared_client.get("/api/me")).json()["reader_index"] == 0

    async def test_a_post_is_attributed_to_the_session_member(self, shared_client):
        sign_in_as(shared_client, "Grace")
        created = await shared_client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Hers."},
        )
        assert created.status_code == 201
        assert created.json()["member"] == "Grace"

    async def test_two_browsers_are_two_people(self, shared_client, shared_container):
        """The whole point. One deployment, one Notion workspace, two members."""
        from httpx import ASGITransport, AsyncClient

        from app.main import create_app

        app = create_app()
        app.state.container = shared_container
        transport = ASGITransport(app=app, raise_app_exceptions=False)

        async with AsyncClient(transport=transport, base_url="https://test") as other:
            sign_in_as(shared_client, "Ada")
            sign_in_as(other, "Grace")

            mine = await shared_client.post(
                "/api/posts",
                json={"book_id": BOOK.value, "type": "Thought", "body": "Mine."},
            )
            theirs = await other.post(
                "/api/posts",
                json={"book_id": BOOK.value, "type": "Thought", "body": "Theirs."},
            )

        assert mine.json()["member"] == "Ada"
        assert theirs.json()["member"] == "Grace"

    async def test_you_can_edit_your_own_post(self, shared_client):
        """The other half of ownership. Without this, a check that refuses
        *everyone* passes the test above just as well as a correct one."""
        sign_in_as(shared_client, "Grace")
        created = await shared_client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Hers."},
        )
        response = await shared_client.patch(
            f"/api/posts/{created.json()['id']}", json={"body": "Revised."}
        )
        assert response.status_code == 200
        assert response.json()["body_preview"] == "Revised."

    async def test_you_cannot_edit_the_other_members_post(self, shared_client):
        """Ownership is now checked against the session rather than against the
        server's configuration, which is what makes the check mean anything on
        a shared deployment."""
        sign_in_as(shared_client, "Ada")
        created = await shared_client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Ada's."},
        )
        post_id = created.json()["id"]

        sign_in_as(shared_client, "Grace")
        response = await shared_client.patch(
            f"/api/posts/{post_id}", json={"body": "Grace's now."}
        )
        assert response.status_code == 403

    async def test_a_leftover_member_name_is_not_an_identity(
        self, shared_settings, uow_factory, seeded
    ):
        """The realistic misconfiguration: someone copies their local `.env`
        into the deployment, `MEMBER_NAME` comes along, and the fallback that
        exists for local use silently attributes every anonymous request to
        that member. Under `passphrase` the configured name means nothing."""
        from httpx import ASGITransport, AsyncClient

        from app.main import create_app

        leftover = shared_settings.model_copy(update={"member_name": "Ada"})
        app = create_app()
        app.state.container = Container(leftover, uow_factory=uow_factory)
        transport = ASGITransport(app=app, raise_app_exceptions=False)

        async with AsyncClient(transport=transport, base_url="https://test") as http:
            assert (await http.get("/api/me")).status_code == 401
            posted = await http.post(
                "/api/posts",
                json={"book_id": BOOK.value, "type": "Thought", "body": "Anon."},
            )
            assert posted.status_code == 401

    async def test_a_forged_cookie_is_refused(self, shared_client):
        from app.interface import session as session_module

        shared_client.cookies.set(
            session_module.COOKIE_NAME, session_module.issue("Ada", "not-the-secret")
        )
        assert (await shared_client.get("/api/me")).status_code == 401

    async def test_a_member_no_longer_on_the_roster_is_refused(self, shared_client):
        """A signature proves the app issued the token, not that the roster
        still contains the name. Removing someone from MEMBERS signs them out."""
        sign_in_as(shared_client, "Mallory")
        assert (await shared_client.get("/api/me")).status_code == 401

    async def test_the_roster_check_folds_case(self, shared_client):
        """Notion's Member column and the roster are both typed by hand."""
        sign_in_as(shared_client, "ada")
        assert (await shared_client.get("/api/me")).status_code == 200


class TestOpenModeIsUnchanged:
    """The local two-machine workflow has to keep working exactly as it did,
    with no login and no new configuration."""

    async def test_no_session_is_needed(self, client):
        assert (await client.get("/api/me")).status_code == 200

    async def test_identity_is_still_the_configured_member(self, client):
        assert (await client.get("/api/me")).json()["member"] == "Ada"

    async def test_a_session_cookie_is_still_honoured_if_present(
        self, container, seeded
    ):
        """So the sign-in flow can be exercised locally without switching
        modes. Configuration is the fallback, not an override."""
        from httpx import ASGITransport, AsyncClient

        from app.interface import session as session_module
        from app.main import create_app

        configured = container.settings.model_copy(
            update={"session_secret": "local-secret"}
        )
        local = Container(configured, uow_factory=container._uow_override)
        app = create_app()
        app.state.container = local
        transport = ASGITransport(app=app, raise_app_exceptions=False)

        async with AsyncClient(transport=transport, base_url="http://test") as http:
            http.cookies.set(
                session_module.COOKIE_NAME,
                session_module.issue("Grace", "local-secret"),
            )
            assert (await http.get("/api/me")).json()["member"] == "Grace"


async def test_me_returns_the_configured_member_and_roster(client):
    """`signed_in` is false: identity came from configuration, and there is no
    session for the browser to end."""
    response = await client.get("/api/me")
    assert response.json() == {
        "member": "Ada",
        "members": ["Ada", "Grace"],
        "reader_index": 0,
        "signed_in": False,
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

    async def test_add_book_with_an_oversize_title_returns_400_not_502(self, client):
        """It used to pass every layer and be refused by Notion, which the
        member read as "Can't reach Notion right now" — a 502 for a typing
        mistake, naming no field."""
        response = await client.post("/api/books", json={"title": "x" * 2001})
        assert response.status_code == 400
        assert response.json() == {
            "error": "That title is 2,001 characters. The limit is 2,000."
        }

    async def test_a_whitespace_author_is_stored_as_no_author(self, client):
        response = await client.post(
            "/api/books", json={"title": "Jonathan Strange", "author": "   "}
        )
        assert response.status_code == 201
        assert response.json()["author"] is None

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
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 20},
        )
        as_ada = await client.get(f"/api/books/{BOOK.value}/feed?as=Ada")
        as_grace = await client.get(f"/api/books/{BOOK.value}/feed?as=Grace")

        assert as_ada.json()["posts"][0]["is_own"] is True
        assert as_grace.json()["posts"][0]["is_own"] is False

    async def test_filtering_the_feed_to_reply_is_refused(self, client):
        """The filter runs over top-level posts after nesting — filtering in
        the query would strip replies off their parents — so `?type=Reply`
        could only ever return an empty feed, and no count in the response
        explained why."""
        response = await client.get(f"/api/books/{BOOK.value}/feed?type=Reply")
        assert response.status_code == 422

    async def test_the_filters_that_are_offered_still_work(self, client):
        for kind in ("Progress", "Thought", "Question"):
            response = await client.get(f"/api/books/{BOOK.value}/feed?type={kind}")
            assert response.status_code == 200, kind

    async def test_view_as_accepts_a_member_whatever_the_case(self, client):
        """Notion's Member column is typed by hand, and the roster is typed
        into a config file. `?as=ada` naming the same person as `Ada` must not
        be a 400."""
        response = await client.get(f"/api/books/{BOOK.value}/feed?as=ada")
        assert response.status_code == 200

    async def test_view_as_still_refuses_someone_who_is_not_a_member(self, client):
        response = await client.get(f"/api/books/{BOOK.value}/feed?as=Bob")
        assert response.status_code == 400

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

    async def test_deleting_the_same_post_twice_returns_404_the_second_time(
        self, client
    ):
        """A deleted post is archived rather than destroyed, so it is still
        there to be found by id. It answered 204 every time until the use
        cases learned to tell the difference."""
        created = await client.post(
            "/api/posts", json={"book_id": BOOK.value, "type": "Thought", "body": "x"}
        )
        post_id = created.json()["id"]
        assert (await client.delete(f"/api/posts/{post_id}")).status_code == 204
        second = await client.delete(f"/api/posts/{post_id}")
        assert second.status_code == 404
        assert second.json() == {"error": "That post is gone."}

    async def test_editing_a_deleted_post_returns_404(self, client):
        created = await client.post(
            "/api/posts", json={"book_id": BOOK.value, "type": "Thought", "body": "x"}
        )
        post_id = created.json()["id"]
        await client.delete(f"/api/posts/{post_id}")
        response = await client.patch(f"/api/posts/{post_id}", json={"body": "Back."})
        assert response.status_code == 404

    async def test_the_body_of_a_deleted_post_returns_404(self, client):
        created = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "y" * 2500},
        )
        post_id = created.json()["id"]
        await client.delete(f"/api/posts/{post_id}")
        assert (await client.get(f"/api/posts/{post_id}/body")).status_code == 404

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

    async def test_an_empty_reply_sent_as_progress_returns_400(self, client):
        """Progress is the one type exempt from needing a body, and a parent
        overrides the requested type — so this combination is how an empty
        reply reached the store."""
        parent = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Parent."},
        )
        response = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Progress",
                "chapter": 9,
                "parent_post_id": parent.json()["id"],
            },
        )
        assert response.status_code == 400
        assert response.json() == {"error": "Write something first."}

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


class TestChapterBoundsOverHttp:
    """The seeded book states 30 chapters. These are the requests a client can
    actually send, including the ones a well-behaved UI never would."""

    async def test_a_chapter_past_the_end_is_a_400_naming_the_book(self, client):
        response = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 99},
        )
        assert response.status_code == 400
        assert response.json() == {
            "error": "Piranesi has 30 chapters, so there is no chapter 99."
        }

    async def test_the_last_chapter_is_accepted(self, client):
        response = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 30},
        )
        assert response.status_code == 201

    async def test_a_refused_post_does_not_appear_in_the_feed(self, client):
        await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 99},
        )
        feed = await client.get(f"/api/books/{BOOK.value}/feed")
        assert feed.json()["posts"] == []

    async def test_editing_a_post_past_the_end_is_a_400(self, client):
        created = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 10},
        )
        response = await client.patch(
            f"/api/posts/{created.json()['id']}", json={"chapter": 99}
        )
        assert response.status_code == 400

    async def test_lowering_a_books_chapter_count_below_a_post_is_a_400(self, client):
        await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 25},
        )
        response = await client.patch(
            f"/api/books/{BOOK.value}", json={"title": "Piranesi", "total_chapters": 20}
        )
        assert response.status_code == 400
        assert "25" in response.json()["error"]

    @pytest.mark.parametrize("chapter", [0, -1, 10_001, 2**63])
    async def test_a_chapter_outside_the_sane_range_is_rejected_by_schema(
        self, client, chapter
    ):
        """422 rather than 400: these are not chapter numbers at all, and they
        must never reach Notion's number property, which round-trips through a
        float and loses precision above 2**53."""
        response = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": chapter},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("page", [0, -1, 100_001])
    async def test_a_page_outside_the_sane_range_is_rejected_by_schema(
        self, client, page
    ):
        response = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Progress",
                "chapter": 5,
                "page": page,
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("total", [0, -1, 10_001])
    async def test_a_total_chapter_count_outside_the_sane_range_is_rejected(
        self, client, total
    ):
        response = await client.post(
            "/api/books", json={"title": "Piranesi", "total_chapters": total}
        )
        assert response.status_code == 422


class TestBodyEndpointWithholdsSpoilers:
    async def _ahead_of_me(self, client):
        """I am at chapter 4; a post lands at chapter 20 from the other member.

        `as=` cannot change attribution, so the spoiler post is written by me
        and then read back as Grace — the only way this installation can hold
        a post it did not write.
        """
        await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Progress", "chapter": 4},
        )
        created = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Thought",
                "chapter": 20,
                "body": "x" * 4000,
            },
        )
        return created.json()["id"]

    async def test_a_long_post_i_wrote_is_returned(self, client):
        post_id = await self._ahead_of_me(client)
        response = await client.get(f"/api/posts/{post_id}/body")
        assert response.status_code == 200
        assert len(response.json()["body"]) == 4000

    async def test_revealing_returns_the_body(self, client):
        post_id = await self._ahead_of_me(client)
        response = await client.get(f"/api/posts/{post_id}/body?reveal=true")
        assert response.status_code == 200

    async def test_an_unknown_post_is_still_a_404(self, client):
        response = await client.get("/api/posts/nope/body")
        assert response.status_code == 404

    # The routes above can only produce posts written by this installation, and
    # your own post is never a spoiler to you. Reaching the withheld case means
    # seeding the other member's post through the same adapters the app uses.
    @pytest.fixture
    async def graces_spoiler(self, seeded):
        uow = seeded()
        async with uow:
            await uow.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=ADA,
                    type=PostType.PROGRESS,
                    position=Position(4),
                )
            )
            post = await uow.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=GRACE,
                    position=Position(40),
                    body_preview="He dies in chapter 40." + "x" * 1800,
                    has_full_body=True,
                ),
                "He dies in chapter 40." + "x" * 3000,
            )
            await uow.commit()
        return post

    async def test_a_spoiler_body_is_withheld_with_403(self, client, graces_spoiler):
        response = await client.get(f"/api/posts/{graces_spoiler.id.value}/body")
        assert response.status_code == 403
        assert response.json() == {"error": "That post is ahead of where you are."}

    async def test_the_withheld_response_carries_none_of_the_text(
        self, client, graces_spoiler
    ):
        response = await client.get(f"/api/posts/{graces_spoiler.id.value}/body")
        assert "dies" not in response.text

    async def test_revealing_a_spoiler_returns_it(self, client, graces_spoiler):
        response = await client.get(
            f"/api/posts/{graces_spoiler.id.value}/body?reveal=true"
        )
        assert response.status_code == 200
        assert response.json()["body"].startswith("He dies in chapter 40.")


class TestBlankIdentifiers:
    """A value object raises on a blank id — correct for a programming error,
    wrong for user input. Built straight from the path, that exception reached
    the catch-all handler and answered 500 to a plainly invalid request.

    Every route that takes an id is listed, because the bug was per-route: one
    fixed route would have left the others crashing.
    """

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/books/%20/feed"),
            ("PATCH", "/api/books/%20"),
            ("GET", "/api/posts/%20/body"),
            ("PATCH", "/api/posts/%20"),
            ("DELETE", "/api/posts/%20"),
        ],
    )
    async def test_a_whitespace_id_in_the_path_is_rejected(self, client, method, path):
        response = await client.request(
            method, path, json={"title": "Piranesi"} if method == "PATCH" else None
        )
        assert response.status_code == 422
        assert response.json() == {"error": "That isn't a valid id."}

    @pytest.mark.parametrize("book_id", ["", "   ", "\t"])
    async def test_a_blank_book_id_in_the_body_is_rejected(self, client, book_id):
        response = await client.post(
            "/api/posts", json={"book_id": book_id, "type": "Thought", "body": "Hi."}
        )
        assert response.status_code == 422

    async def test_a_whitespace_parent_post_id_is_rejected(self, client):
        """Whitespace is truthy, so this used to pass the `if` in the router and
        reach the value object."""
        response = await client.post(
            "/api/posts",
            json={
                "book_id": BOOK.value,
                "type": "Thought",
                "body": "Hi.",
                "parent_post_id": "   ",
            },
        )
        assert response.status_code == 422

    async def test_an_absent_parent_post_id_is_still_fine(self, client):
        response = await client.post(
            "/api/posts",
            json={"book_id": BOOK.value, "type": "Thought", "body": "Hi."},
        )
        assert response.status_code == 201

    async def test_a_surrounding_space_on_a_real_id_is_tolerated(self, client):
        """Stripped, not rejected — a copied-and-pasted id often carries one."""
        response = await client.post(
            "/api/posts",
            json={"book_id": f" {BOOK.value} ", "type": "Thought", "body": "Hi."},
        )
        assert response.status_code == 201

    async def test_an_unknown_but_well_formed_id_is_still_a_404(self, client):
        """422 is for an id that cannot exist; 404 for one that simply does not."""
        response = await client.get("/api/books/nope/feed")
        assert response.status_code == 404
