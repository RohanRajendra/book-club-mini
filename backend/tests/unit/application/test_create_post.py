"""CreatePost — the most rule-dense object in the app.

Each rule here is a decision from 01-ux-spec.md, restated in the test name.
"""

from __future__ import annotations

import pytest

from app.adapters.memory import InMemoryUnitOfWork
from app.application.use_cases.create_post import CreatePost, CreatePostCommand
from app.domain import errors
from app.domain.entities import Book
from app.domain.values import BookId, MemberName, Position, PostId, PostType
from tests.builders import ADA, GRACE, ROSTER, at_minute, long_body, make_post

BOOK = BookId("book-1")
OTHER_BOOK = BookId("book-2")


@pytest.fixture
def uow():
    return InMemoryUnitOfWork(clock=lambda: at_minute(0))


@pytest.fixture
async def seeded(uow):
    async with uow:
        await uow.books.add(Book(id=BOOK, title="Piranesi"))
        await uow.books.add(Book(id=OTHER_BOOK, title="Jonathan Strange"))
        await uow.commit()
    return uow


@pytest.fixture
def create(seeded):
    return CreatePost(uow_factory=lambda: seeded, roster=ROSTER)


def command(**overrides) -> CreatePostCommand:
    return CreatePostCommand(
        **{
            "book_id": BOOK,
            "member": ADA,
            "type": PostType.THOUGHT,
            "body": "The statues are the point.",
            "chapter": 9,
            "page": 204,
            "parent_post_id": None,
            **overrides,
        }
    )


async def test_creates_a_thought_with_a_position(create):
    result = await create.execute(command())
    post = result.unwrap()
    assert post.type is PostType.THOUGHT
    assert post.position == Position(9, 204)
    assert post.id is not None


async def test_creates_a_progress_post_with_no_body(create):
    """A bare position is a valid post."""
    result = await create.execute(
        command(type=PostType.PROGRESS, body="", page=None)
    )
    assert result.unwrap().body_preview == ""


async def test_progress_without_a_chapter_returns_chapter_required_error(create):
    result = await create.execute(
        command(type=PostType.PROGRESS, chapter=None, page=None, body="")
    )
    assert isinstance(result.unwrap_err(), errors.ChapterRequiredForProgress)


async def test_page_without_a_chapter_returns_page_requires_chapter_error(create):
    """A page number alone cannot be compared against anyone's position."""
    result = await create.execute(command(chapter=None, page=204))
    assert isinstance(result.unwrap_err(), errors.PageRequiresChapter)


async def test_thought_without_a_body_returns_body_required_error(create):
    result = await create.execute(command(body="   "))
    assert isinstance(result.unwrap_err(), errors.BodyRequired)


async def test_question_without_a_body_returns_body_required_error(create):
    result = await create.execute(command(type=PostType.QUESTION, body=""))
    assert isinstance(result.unwrap_err(), errors.BodyRequired)


async def test_thought_without_a_chapter_is_accepted(create):
    """Such a post can never be blurred for anyone. That is the member's
    choice and the app does not warn about it."""
    result = await create.execute(command(chapter=None, page=None))
    assert result.unwrap().position is None


async def test_body_over_the_limit_returns_body_too_long_error(create):
    result = await create.execute(command(body="x" * 200_001))
    assert isinstance(result.unwrap_err(), errors.BodyTooLong)


async def test_unknown_book_returns_book_not_found(create):
    result = await create.execute(command(book_id=BookId("nope")))
    assert isinstance(result.unwrap_err(), errors.BookNotFound)


async def test_member_not_in_roster_returns_unknown_member(create):
    result = await create.execute(command(member=MemberName("Alan")))
    assert isinstance(result.unwrap_err(), errors.UnknownMember)


async def test_long_body_is_split_into_preview_and_full_body(create, seeded):
    body = long_body(4000)
    post = (await create.execute(command(body=body))).unwrap()
    assert post.has_full_body
    assert len(post.body_preview) <= 1900
    async with seeded:
        assert await seeded.posts.get_full_body(post.id) == body


async def test_successful_creation_commits_the_unit_of_work(create, seeded):
    post = (await create.execute(command())).unwrap()
    async with seeded:
        assert await seeded.posts.get(post.id) is not None


async def test_a_failed_validation_does_not_write_anything(create, seeded):
    await create.execute(command(body=""))
    async with seeded:
        assert await seeded.posts.list_for_book(BOOK) == []


class TestReplies:
    @pytest.fixture
    async def parent(self, seeded):
        async with seeded:
            parent = await seeded.posts.add(
                make_post(id=None, book_id=BOOK, member=GRACE, position=Position(12, 301))
            )
            await seeded.commit()
        return parent

    async def test_reply_forces_type_to_reply(self, create, parent):
        result = await create.execute(
            command(type=PostType.THOUGHT, parent_post_id=parent.id)
        )
        assert result.unwrap().type is PostType.REPLY

    async def test_reply_copies_the_parents_position_ignoring_any_supplied(
        self, create, parent
    ):
        """Copying rather than joining keeps spoiler evaluation lookup-free."""
        result = await create.execute(
            command(parent_post_id=parent.id, chapter=1, page=1)
        )
        assert result.unwrap().position == Position(12, 301)

    async def test_reply_to_a_reply_returns_cannot_reply_to_reply(
        self, create, seeded, parent
    ):
        async with seeded:
            reply = await seeded.posts.add(
                make_post(
                    id=None,
                    book_id=BOOK,
                    type=PostType.REPLY,
                    parent_post_id=parent.id,
                    position=parent.position,
                )
            )
            await seeded.commit()
        result = await create.execute(command(parent_post_id=reply.id))
        assert isinstance(result.unwrap_err(), errors.CannotReplyToReply)

    async def test_reply_to_a_post_in_another_book_returns_reply_book_mismatch(
        self, create, parent
    ):
        result = await create.execute(
            command(book_id=OTHER_BOOK, parent_post_id=parent.id)
        )
        assert isinstance(result.unwrap_err(), errors.ReplyBookMismatch)

    async def test_reply_to_a_missing_parent_returns_post_not_found(self, create):
        result = await create.execute(command(parent_post_id=PostId("nope")))
        assert isinstance(result.unwrap_err(), errors.PostNotFound)

    async def test_reply_without_a_body_returns_body_required(self, create, parent):
        result = await create.execute(command(parent_post_id=parent.id, body=""))
        assert isinstance(result.unwrap_err(), errors.BodyRequired)

    async def test_reply_to_a_parent_with_no_position_has_no_position(
        self, create, seeded
    ):
        async with seeded:
            parent = await seeded.posts.add(
                make_post(id=None, book_id=BOOK, position=None)
            )
            await seeded.commit()
        result = await create.execute(command(parent_post_id=parent.id))
        assert result.unwrap().position is None
