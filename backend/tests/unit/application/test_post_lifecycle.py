"""EditPost, DeletePost and GetPostBody."""

from __future__ import annotations

import pytest

from app.adapters.memory import InMemoryUnitOfWork
from app.application.use_cases.create_post import CreatePost, CreatePostCommand
from app.application.use_cases.delete_post import DeletePost, DeletePostCommand
from app.application.use_cases.edit_post import EditPost, EditPostCommand
from app.application.use_cases.get_post_body import GetPostBody, PostBodyQuery
from app.domain import errors
from app.domain.entities import Book
from app.domain.policies import ChapterFirstSpoilerPolicy
from app.domain.services import PositionResolver
from app.domain.values import BookId, Position, PostId, PostType
from tests.builders import ADA, GRACE, at_minute, long_body, make_post, make_reply

BOOK = BookId("book-1")


def body_query(post_id, viewer=ADA, reveal=False) -> PostBodyQuery:
    return PostBodyQuery(post_id=post_id, viewer=viewer, reveal=reveal)


@pytest.fixture
def uow():
    store = InMemoryUnitOfWork(clock=lambda: at_minute(0))
    return store


@pytest.fixture
async def seeded(uow):
    async with uow:
        await uow.books.add(Book(id=BOOK, title="Piranesi"))
        await uow.commit()
    return uow


class TestEditPost:
    @pytest.fixture
    def edit(self, seeded):
        return EditPost(uow_factory=lambda: seeded)

    @pytest.fixture
    async def existing(self, seeded):
        async with seeded:
            post = await seeded.posts.add(
                make_post(id=None, book_id=BOOK, member=ADA, body_preview="Original.")
            )
            await seeded.commit()
        return post

    async def test_owner_can_edit_their_own_post(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Revised.", chapter=9)
        )
        assert result.unwrap().body_preview == "Revised."

    async def test_non_owner_returns_not_post_owner(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=GRACE, body="Mine now.", chapter=9)
        )
        assert isinstance(result.unwrap_err(), errors.NotPostOwner)

    async def test_missing_post_returns_post_not_found(self, edit):
        result = await edit.execute(
            EditPostCommand(post_id=PostId("nope"), member=ADA, body="x", chapter=1)
        )
        assert isinstance(result.unwrap_err(), errors.PostNotFound)

    async def test_editing_recomputes_preview_and_has_full_body(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(
                post_id=existing.id, member=ADA, body=long_body(4000), chapter=9
            )
        )
        post = result.unwrap()
        assert post.has_full_body is True
        assert len(post.body_preview) <= 1900

    async def test_editing_long_to_short_clears_the_full_body(
        self, edit, seeded, existing
    ):
        await edit.execute(
            EditPostCommand(
                post_id=existing.id, member=ADA, body=long_body(4000), chapter=9
            )
        )
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Short now.", chapter=9)
        )
        assert result.unwrap().has_full_body is False
        async with seeded:
            assert await seeded.posts.get_full_body(existing.id) == "Short now."

    async def test_editing_short_to_long_stores_a_full_body(
        self, edit, seeded, existing
    ):
        body = long_body(4000)
        await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body=body, chapter=9)
        )
        async with seeded:
            assert await seeded.posts.get_full_body(existing.id) == body

    async def test_editing_a_progress_chapter_changes_the_resolved_position(
        self, edit, seeded
    ):
        async with seeded:
            progress = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=ADA,
                    type=PostType.PROGRESS,
                    position=Position(40),
                    body_preview="",
                )
            )
            await seeded.commit()

        await edit.execute(
            EditPostCommand(post_id=progress.id, member=ADA, body="", chapter=4)
        )

        async with seeded:
            posts = await seeded.posts.list_for_book(BOOK)
        assert PositionResolver().resolve(posts) == {ADA: Position(4)}

    async def test_editing_does_not_change_the_positions_copied_onto_replies(
        self, edit, seeded, existing
    ):
        """A reply's position is a snapshot of where the conversation started;
        editing the parent does not rewrite history."""
        async with seeded:
            reply = await seeded.posts.add(make_reply(existing, GRACE, id=None))
            await seeded.commit()

        await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Moved.", chapter=99)
        )

        async with seeded:
            assert (await seeded.posts.get(reply.id)).position == existing.position

    async def test_editing_a_reply_keeps_its_copied_position(self, edit, seeded, existing):
        async with seeded:
            reply = await seeded.posts.add(make_reply(existing, ADA, id=None))
            await seeded.commit()

        result = await edit.execute(
            EditPostCommand(post_id=reply.id, member=ADA, body="Rewritten.", chapter=1)
        )
        assert result.unwrap().position == existing.position

    async def test_editing_a_progress_post_without_a_chapter_is_rejected(
        self, edit, seeded
    ):
        async with seeded:
            progress = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=ADA,
                    type=PostType.PROGRESS,
                    position=Position(4),
                    body_preview="",
                )
            )
            await seeded.commit()
        result = await edit.execute(
            EditPostCommand(post_id=progress.id, member=ADA, body="", chapter=None)
        )
        assert isinstance(result.unwrap_err(), errors.ChapterRequiredForProgress)

    async def test_editing_a_thought_to_an_empty_body_is_rejected(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="  ", chapter=9)
        )
        assert isinstance(result.unwrap_err(), errors.BodyRequired)

    async def test_editing_with_a_page_but_no_chapter_is_rejected(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="x", page=204)
        )
        assert isinstance(result.unwrap_err(), errors.PageRequiresChapter)

    async def test_editing_beyond_the_body_ceiling_is_rejected(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(
                post_id=existing.id, member=ADA, body="x" * 200_001, chapter=9
            )
        )
        assert isinstance(result.unwrap_err(), errors.BodyTooLong)

    async def test_clearing_the_chapter_on_a_thought_removes_its_position(
        self, edit, existing
    ):
        """A thought with the chapter cleared can never be blurred for anyone.
        That is the member's choice and the app does not warn about it."""
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="No position.")
        )
        assert result.unwrap().position is None


class TestDeletePost:
    @pytest.fixture
    def delete(self, seeded):
        return DeletePost(uow_factory=lambda: seeded)

    @pytest.fixture
    async def parent(self, seeded):
        async with seeded:
            post = await seeded.posts.add(make_post(id=None, book_id=BOOK, member=ADA))
            await seeded.commit()
        return post

    async def test_owner_can_delete_their_own_post(self, delete, seeded, parent):
        result = await delete.execute(DeletePostCommand(post_id=parent.id, member=ADA))
        assert result.unwrap() == 1
        async with seeded:
            assert await seeded.posts.list_for_book(BOOK) == []

    async def test_non_owner_returns_not_post_owner(self, delete, parent):
        result = await delete.execute(DeletePostCommand(post_id=parent.id, member=GRACE))
        assert isinstance(result.unwrap_err(), errors.NotPostOwner)

    async def test_missing_post_returns_post_not_found(self, delete):
        result = await delete.execute(
            DeletePostCommand(post_id=PostId("nope"), member=ADA)
        )
        assert isinstance(result.unwrap_err(), errors.PostNotFound)

    async def test_deleting_a_post_archives_its_replies(self, delete, seeded, parent):
        async with seeded:
            await seeded.posts.add(make_reply(parent, GRACE, id=None))
            await seeded.posts.add(make_reply(parent, ADA, id=None))
            await seeded.commit()

        result = await delete.execute(DeletePostCommand(post_id=parent.id, member=ADA))
        assert result.unwrap() == 3
        async with seeded:
            assert await seeded.posts.list_for_book(BOOK) == []

    async def test_replies_are_archived_before_the_parent(self, delete, seeded, parent):
        """A failure partway through then leaves the parent visible with some
        replies missing, rather than a vanished parent with orphans."""
        async with seeded:
            reply = await seeded.posts.add(make_reply(parent, GRACE, id=None))
            await seeded.commit()
        seeded.posts.calls.clear()

        await delete.execute(DeletePostCommand(post_id=parent.id, member=ADA))

        archived = [call for call in seeded.posts.calls if call[0] == "archive"]
        assert archived == [("archive", reply.id.value), ("archive", parent.id.value)]

    async def test_deleting_a_reply_does_not_touch_its_parent(
        self, delete, seeded, parent
    ):
        async with seeded:
            reply = await seeded.posts.add(make_reply(parent, ADA, id=None))
            await seeded.commit()

        result = await delete.execute(DeletePostCommand(post_id=reply.id, member=ADA))
        assert result.unwrap() == 1
        async with seeded:
            listed = await seeded.posts.list_for_book(BOOK)
        assert [post.id for post in listed] == [parent.id]

    async def test_a_failure_partway_through_triggers_compensation(
        self, delete, seeded, parent
    ):
        """The unit of work rolls back, so a half-finished cascade does not
        leave replies archived under a surviving parent."""
        async with seeded:
            reply = await seeded.posts.add(make_reply(parent, GRACE, id=None))
            await seeded.commit()

        original = seeded.posts.archive
        calls = {"n": 0}

        async def failing(post_id):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("Notion said no")
            await original(post_id)

        seeded.posts.archive = failing
        with pytest.raises(RuntimeError):
            await delete.execute(DeletePostCommand(post_id=parent.id, member=ADA))
        seeded.posts.archive = original

        async with seeded:
            listed = {post.id for post in await seeded.posts.list_for_book(BOOK)}
        assert listed == {parent.id, reply.id}


class TestGetPostBody:
    @pytest.fixture
    def get_body(self, seeded):
        return GetPostBody(
            uow_factory=lambda: seeded,
            spoiler_policy=ChapterFirstSpoilerPolicy(),
            position_resolver=PositionResolver(),
        )

    async def test_returns_the_preview_when_the_post_has_no_full_body(
        self, get_body, seeded
    ):
        async with seeded:
            post = await seeded.posts.add(
                make_post(id=None, book_id=BOOK, body_preview="Short.")
            )
            await seeded.commit()
        assert (await get_body.execute(body_query(post.id))).unwrap() == "Short."

    async def test_fetches_the_full_body_when_has_full_body_is_true(
        self, get_body, seeded
    ):
        body = long_body(4000)
        async with seeded:
            post = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    body_preview=body[:1900],
                    has_full_body=True,
                ),
                body,
            )
            await seeded.commit()
        assert (await get_body.execute(body_query(post.id))).unwrap() == body

    async def test_does_not_call_get_full_body_when_has_full_body_is_false(
        self, get_body, seeded
    ):
        """The point of the whole preview/full-body split: one saved request.
        Asserted against the repository's call log, not a mock
."""
        async with seeded:
            post = await seeded.posts.add(
                make_post(id=None, book_id=BOOK, body_preview="Short.")
            )
            await seeded.commit()
        seeded.posts.calls.clear()

        await get_body.execute(body_query(post.id))

        assert not [call for call in seeded.posts.calls if call[0] == "get_full_body"]

    async def test_missing_post_returns_post_not_found(self, get_body):
        result = await get_body.execute(body_query(PostId("nope")))
        assert isinstance(result.unwrap_err(), errors.PostNotFound)


class TestEditPostChapterBounds:
    """EditPost was the weaker of the two write paths: it never loaded the
    book, so it had nothing to bound a chapter against."""

    BOUNDED = BookId("book-bounded")

    @pytest.fixture
    async def edit(self, uow):
        async with uow:
            await uow.books.add(
                Book(id=self.BOUNDED, title="Piranesi", total_chapters=45)
            )
            await uow.commit()
        return EditPost(uow_factory=lambda: uow)

    @pytest.fixture
    async def existing(self, uow):
        async with uow:
            post = await uow.posts.add(
                make_post(
                    id=None,
                    book_id=self.BOUNDED,
                    member=ADA,
                    position=Position(10),
                    body_preview="Original.",
                )
            )
            await uow.commit()
        return post

    async def test_moving_a_post_past_the_end_is_refused(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Revised.", chapter=99)
        )
        assert isinstance(result.unwrap_err(), errors.ChapterBeyondBook)

    async def test_moving_to_the_last_chapter_is_accepted(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Revised.", chapter=45)
        )
        assert result.unwrap().position == Position(45)

    async def test_the_post_is_unchanged_when_the_chapter_is_refused(
        self, edit, existing, uow
    ):
        await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Revised.", chapter=99)
        )
        async with uow:
            stored = await uow.posts.get(existing.id)
        assert stored.body_preview == "Original."
        assert stored.position == Position(10)

    async def test_clearing_the_position_is_still_allowed(self, edit, existing):
        result = await edit.execute(
            EditPostCommand(post_id=existing.id, member=ADA, body="Revised.")
        )
        assert result.unwrap().position is None

    async def test_a_post_whose_book_has_vanished_reports_it(self, uow):
        """Previously EditPost never read the book, so it could not notice."""
        async with uow:
            post = await uow.posts.add(
                make_post(id=None, book_id=BookId("gone"), member=ADA)
            )
            await uow.commit()

        edit = EditPost(uow_factory=lambda: uow)
        result = await edit.execute(
            EditPostCommand(post_id=post.id, member=ADA, body="Revised.", chapter=3)
        )
        assert isinstance(result.unwrap_err(), errors.BookNotFound)


class TestDeletedPostsAreNotOperable:
    """A deleted post is archived, not destroyed, and stays retrievable by id.

    That is deliberate — a mistaken deletion has to be recoverable. It also
    means every use case that reads a post by id has to notice, because
    otherwise a deleted post answers exactly like a live one: editing it
    returned 200, deleting it twice returned 204 twice, and its body was still
    fetchable.
    """

    @pytest.fixture
    async def deleted(self, seeded):
        async with seeded:
            post = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=ADA,
                    body_preview="Gone.",
                    position=Position(9),
                )
            )
            await seeded.posts.archive(post.id)
            await seeded.commit()
        return post

    async def test_editing_a_deleted_post_reports_it_gone(self, seeded, deleted):
        result = await EditPost(uow_factory=lambda: seeded).execute(
            EditPostCommand(post_id=deleted.id, member=ADA, body="Back.", chapter=9)
        )
        assert isinstance(result.unwrap_err(), errors.PostNotFound)

    async def test_deleting_a_deleted_post_reports_it_gone(self, seeded, deleted):
        result = await DeletePost(uow_factory=lambda: seeded).execute(
            DeletePostCommand(post_id=deleted.id, member=ADA)
        )
        assert isinstance(result.unwrap_err(), errors.PostNotFound)

    async def test_the_body_of_a_deleted_post_is_not_served(self, seeded, deleted):
        result = await GetPostBody(
            uow_factory=lambda: seeded,
            spoiler_policy=ChapterFirstSpoilerPolicy(),
            position_resolver=PositionResolver(),
        ).execute(body_query(deleted.id))
        assert isinstance(result.unwrap_err(), errors.PostNotFound)

    async def test_replying_to_a_deleted_post_reports_it_gone(self, seeded, deleted):
        """Not in the original report, but the same read: a reply to an
        archived parent would be created and then never appear."""
        create = CreatePost(uow_factory=lambda: seeded, roster=[ADA, GRACE])
        result = await create.execute(
            CreatePostCommand(
                book_id=BOOK,
                member=GRACE,
                type=PostType.THOUGHT,
                body="Agreed.",
                parent_post_id=deleted.id,
            )
        )
        assert isinstance(result.unwrap_err(), errors.PostNotFound)


class TestGetPostBodyWithholdsSpoilers:
    """The feed flags a spoiler and the client blurs it. Before this, the body
    endpoint handed over the whole text to anyone who asked by id, so the app's
    central feature was a client-side visual effect."""

    @pytest.fixture
    def get_body(self, seeded):
        return GetPostBody(
            uow_factory=lambda: seeded,
            spoiler_policy=ChapterFirstSpoilerPolicy(),
            position_resolver=PositionResolver(),
        )

    @pytest.fixture
    async def ahead(self, seeded):
        """Grace posts at chapter 40; Ada is at chapter 4."""
        async with seeded:
            await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=ADA,
                    type=PostType.PROGRESS,
                    position=Position(4),
                    created_at=at_minute(0),
                )
            )
            post = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=GRACE,
                    body_preview="He dies in chapter 40.",
                    position=Position(40),
                )
            )
            await seeded.commit()
        return post

    async def test_a_post_ahead_of_the_viewer_is_withheld(self, get_body, ahead):
        result = await get_body.execute(body_query(ahead.id))
        assert isinstance(result.unwrap_err(), errors.SpoilerWithheld)

    async def test_the_text_is_not_in_the_error(self, get_body, ahead):
        message = (await get_body.execute(body_query(ahead.id))).unwrap_err().message
        assert "chapter 40" not in message
        assert "dies" not in message

    async def test_revealing_it_returns_the_body(self, get_body, ahead):
        """Read anyway is a deliberate choice, and the server has to be told."""
        result = await get_body.execute(body_query(ahead.id, reveal=True))
        assert result.unwrap() == "He dies in chapter 40."

    async def test_the_member_who_wrote_it_always_gets_it(self, get_body, ahead):
        result = await get_body.execute(body_query(ahead.id, viewer=GRACE))
        assert result.unwrap() == "He dies in chapter 40."

    async def test_a_post_behind_the_viewer_is_returned(self, get_body, seeded):
        async with seeded:
            await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=ADA,
                    type=PostType.PROGRESS,
                    position=Position(40),
                    created_at=at_minute(0),
                )
            )
            post = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=GRACE,
                    body_preview="Chapter four was slow.",
                    position=Position(4),
                )
            )
            await seeded.commit()

        assert (await get_body.execute(body_query(post.id))).unwrap() == (
            "Chapter four was slow."
        )

    async def test_a_viewer_with_no_position_sees_everything(self, get_body, seeded):
        """Matches the feed: someone who has not said where they are cannot be
        spoiled by a rule that has nothing to compare against."""
        async with seeded:
            post = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    member=GRACE,
                    body_preview="He dies in chapter 40.",
                    position=Position(40),
                )
            )
            await seeded.commit()

        assert (await get_body.execute(body_query(post.id))).unwrap() == (
            "He dies in chapter 40."
        )

    async def test_revealing_costs_no_extra_query(self, get_body, ahead, seeded):
        """The spoiler check reads the book's posts. Once the member has
        revealed the post that work is pointless, so it is skipped."""
        seeded.posts.calls.clear()
        await get_body.execute(body_query(ahead.id, reveal=True))
        assert "list_for_book" not in [name for name, _ in seeded.posts.calls]

    async def test_withholding_does_read_the_posts(self, get_body, ahead, seeded):
        seeded.posts.calls.clear()
        await get_body.execute(body_query(ahead.id))
        assert "list_for_book" in [name for name, _ in seeded.posts.calls]
