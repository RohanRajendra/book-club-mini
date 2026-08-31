"""Create a post, a progress update, or a reply."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.application.position_rules import chapter_beyond_book
from app.domain import errors
from app.domain.entities import Post
from app.domain.result import Err, Ok, Result
from app.domain.services import MAX_BODY, BodySplitter
from app.domain.values import BookId, MemberName, Position, PostId, PostType
from app.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class CreatePostCommand:
    book_id: BookId
    member: MemberName
    type: PostType
    body: str = ""
    chapter: int | None = None
    page: int | None = None
    parent_post_id: PostId | None = None


class CreatePost:
    """Position pre-filling for thoughts and questions is a *frontend* concern.

    This use case takes what it is given. Defaulting the position here would
    make it impossible for a member to deliberately post without one.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        roster: list[MemberName],
        splitter: BodySplitter | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._roster = roster
        self._splitter = splitter or BodySplitter()

    async def execute(self, command: CreatePostCommand) -> Result[Post]:
        if command.member not in self._roster:
            return Err(errors.UnknownMember(f"{command.member} is not in this club."))

        is_reply = command.parent_post_id is not None

        # Replies copy their parent's position, so anything supplied is ignored
        # and validating it would reject input that has no effect.
        if not is_reply:
            invalid = self._validate_position(command)
            if invalid is not None:
                return Err(invalid)

        if command.type is not PostType.PROGRESS and not command.body.strip():
            return Err(errors.BodyRequired("Write something first."))

        if len(command.body) > MAX_BODY:
            return Err(
                errors.BodyTooLong(
                    f"That post is {len(command.body):,} characters. "
                    f"The limit is {MAX_BODY:,}."
                )
            )

        uow = self._uow_factory()
        async with uow:
            book = await uow.books.get(command.book_id)
            if book is None:
                return Err(errors.BookNotFound("That book isn't here."))

            # Needs the book, so it cannot join the checks above. A chapter
            # past the end is not a cosmetic error: PositionResolver would put
            # the member there, and nothing would be ahead of them, so blurring
            # would switch off for the whole book.
            if (
                not is_reply
                and command.chapter is not None
                and not book.contains_chapter(command.chapter)
            ):
                return Err(chapter_beyond_book(book, command.chapter))

            post_type = command.type
            position: Position | None

            if is_reply:
                parent = await uow.posts.get(command.parent_post_id)
                if parent is None:
                    return Err(errors.PostNotFound("That post is gone."))
                if parent.is_reply:
                    return Err(
                        errors.CannotReplyToReply("Replies are one level deep.")
                    )
                if parent.book_id != command.book_id:
                    return Err(
                        errors.ReplyBookMismatch(
                            "That post belongs to a different book."
                        )
                    )
                post_type = PostType.REPLY
                position = parent.position
            else:
                position = (
                    Position(command.chapter, command.page)
                    if command.chapter is not None
                    else None
                )

            preview, has_full_body, full_body = self._splitter.split(command.body)

            created = await uow.posts.add(
                Post(
                    book_id=command.book_id,
                    member=command.member,
                    type=post_type,
                    body_preview=preview,
                    has_full_body=has_full_body,
                    position=position,
                    parent_post_id=command.parent_post_id,
                ),
                full_body,
            )
            await uow.commit()
            return Ok(created)

    def _validate_position(self, command: CreatePostCommand) -> errors.DomainError | None:
        if command.type is PostType.PROGRESS and command.chapter is None:
            return errors.ChapterRequiredForProgress("Progress needs a chapter number.")
        if command.page is not None and command.chapter is None:
            return errors.PageRequiresChapter("A page needs a chapter to go with it.")
        return None
