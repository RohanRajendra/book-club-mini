"""Fetch a post's complete body, on demand."""

from __future__ import annotations

from typing import Callable

from app.domain import errors
from app.domain.result import Err, Ok, Result
from app.domain.values import PostId
from app.ports.unit_of_work import UnitOfWork


class GetPostBody:
    """The point of the preview/full-body split.

    When `has_full_body` is false the preview *is* the body, so no second
    request is made. That saved request is the whole reason the flag exists.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, post_id: PostId) -> Result[str]:
        uow = self._uow_factory()
        async with uow:
            post = await uow.posts.get(post_id)
            if post is None:
                return Err(errors.PostNotFound("That post is gone."))
            if not post.has_full_body:
                return Ok(post.body_preview)
            return Ok(await uow.posts.get_full_body(post_id))
