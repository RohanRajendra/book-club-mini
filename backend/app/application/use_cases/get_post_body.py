"""Fetch a post's complete body, on demand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.domain import errors
from app.domain.policies import SpoilerPolicy
from app.domain.result import Err, Ok, Result
from app.domain.services import PositionResolver
from app.domain.values import MemberName, PostId
from app.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class PostBodyQuery:
    post_id: PostId
    viewer: MemberName
    #: Set when the member has chosen to read past their position. Without it a
    #: post that is a spoiler for them is withheld.
    reveal: bool = False


class GetPostBody:
    """The point of the preview/full-body split.

    When `has_full_body` is false the preview *is* the body, so no second
    request is made. That saved request is the whole reason the flag exists.

    The spoiler rule applies here too. The feed marks a post as a spoiler and
    the client blurs it, but blurring is a visual effect — this endpoint used to
    hand over the entire body to anyone who asked for it by id, which made the
    app's central feature a matter of client-side good behaviour. Now the body
    is withheld unless the member says they want it.

    Like the ownership checks, this prevents an accident rather than an attack:
    both members are trusted and either could pass `reveal`. What it stops is a
    body arriving that nobody asked to see.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        spoiler_policy: SpoilerPolicy,
        position_resolver: PositionResolver,
    ) -> None:
        self._uow_factory = uow_factory
        self._spoilers = spoiler_policy
        self._positions = position_resolver

    async def execute(self, query: PostBodyQuery) -> Result[str]:
        uow = self._uow_factory()
        async with uow:
            post = await uow.posts.get(query.post_id)
            if post is None:
                return Err(errors.PostNotFound("That post is gone."))

            # Costs one query, and only on the path that was already going to
            # make two. Skipped entirely once the member has revealed the post,
            # which is the common case for a long one.
            if not query.reveal:
                positions = self._positions.resolve(
                    await uow.posts.list_for_book(post.book_id)
                )
                if self._spoilers.is_spoiler(
                    post, query.viewer, positions.get(query.viewer)
                ):
                    return Err(
                        errors.SpoilerWithheld(
                            "That post is ahead of where you are."
                        )
                    )

            if not post.has_full_body:
                return Ok(post.body_preview)
            return Ok(await uow.posts.get_full_body(query.post_id))
