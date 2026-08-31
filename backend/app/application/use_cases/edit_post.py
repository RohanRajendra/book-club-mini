"""Edit one of your own posts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from app.application.position_rules import chapter_beyond_book
from app.domain import errors
from app.domain.entities import Post
from app.domain.result import Err, Ok, Result
from app.domain.services import MAX_BODY, BodySplitter
from app.domain.values import MemberName, Position, PostId, PostType
from app.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class EditPostCommand:
    post_id: PostId
    member: MemberName
    body: str = ""
    chapter: int | None = None
    page: int | None = None


class EditPost:
    """The ownership check prevents accidents, not attacks.

    Each installation declares its own MEMBER_NAME and could declare anything,
    so this is trivially bypassable. It is here so that two people sharing a
    screen cannot clobber each other's posts, which is what it is for.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        splitter: BodySplitter | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._splitter = splitter or BodySplitter()

    async def execute(self, command: EditPostCommand) -> Result[Post]:
        if len(command.body) > MAX_BODY:
            return Err(
                errors.BodyTooLong(
                    f"That post is {len(command.body):,} characters. "
                    f"The limit is {MAX_BODY:,}."
                )
            )

        uow = self._uow_factory()
        async with uow:
            post = await uow.posts.get(command.post_id)
            if post is None:
                return Err(errors.PostNotFound("That post is gone."))
            if post.member != command.member:
                return Err(errors.NotPostOwner("You can only edit your own posts."))

            if post.type is PostType.PROGRESS and command.chapter is None:
                return Err(
                    errors.ChapterRequiredForProgress("Progress needs a chapter number.")
                )
            if command.page is not None and command.chapter is None:
                return Err(
                    errors.PageRequiresChapter("A page needs a chapter to go with it.")
                )
            if post.type is not PostType.PROGRESS and not command.body.strip():
                return Err(errors.BodyRequired("Write something first."))

            # The book read exists only for this check, and a reply's position
            # is a snapshot that editing never moves — so a reply does not pay
            # for it.
            if not post.is_reply and command.chapter is not None:
                book = await uow.books.get(post.book_id)
                if book is None:
                    return Err(errors.BookNotFound("That book isn't here."))
                if not book.contains_chapter(command.chapter):
                    return Err(chapter_beyond_book(book, command.chapter))

            preview, has_full_body, full_body = self._splitter.split(command.body)

            # A reply's position is a snapshot of where the conversation
            # started, so editing one never moves it.
            position = (
                post.position
                if post.is_reply
                else (
                    Position(command.chapter, command.page)
                    if command.chapter is not None
                    else None
                )
            )

            updated = await uow.posts.update(
                replace(
                    post,
                    body_preview=preview,
                    has_full_body=has_full_body,
                    position=position,
                ),
                full_body,
            )
            await uow.commit()
            return Ok(updated)
