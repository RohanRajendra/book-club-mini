"""Delete one of your own posts, and its replies with it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.application.post_access import post_is_gone
from app.domain import errors
from app.domain.result import Err, Ok, Result
from app.domain.values import MemberName, PostId
from app.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class DeletePostCommand:
    post_id: PostId
    member: MemberName


class DeletePost:
    """Notion does not cascade, so replies are archived explicitly.

    Replies go **first**. A failure partway through then leaves the parent
    visible with some replies missing, rather than a vanished parent with
    orphans still counting against the query budget.

    This is the second operation that justifies the unit of work: the whole
    delete runs inside one scope, so a failure triggers compensation.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: DeletePostCommand) -> Result[int]:
        """Returns the number of posts archived, parent included."""
        uow = self._uow_factory()
        async with uow:
            post = await uow.posts.get(command.post_id)
            gone = post_is_gone(post)
            if gone is not None:
                return Err(gone)
            if post.member != command.member:
                return Err(errors.NotPostOwner("You can only delete your own posts."))

            replies = [
                other
                for other in await uow.posts.list_for_book(post.book_id)
                if other.parent_post_id == post.id
            ]
            for reply in replies:
                await uow.posts.archive(reply.id)
            await uow.posts.archive(post.id)

            await uow.commit()
            return Ok(len(replies) + 1)
