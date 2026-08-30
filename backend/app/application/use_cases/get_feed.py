"""Load one book's feed for one viewer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.application.dto import Feed
from app.application.feed import FeedAssembler
from app.domain import errors
from app.domain.result import Err, Ok, Result
from app.domain.values import BookId, MemberName, PostType
from app.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class FeedQuery:
    book_id: BookId
    viewer: MemberName
    post_type: PostType | None = None


class GetFeed:
    """One data-source query per feed load, plus one book read, and no
    per-post requests. That last clause is the property the rate limit makes
    load-bearing."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        assembler: FeedAssembler,
    ) -> None:
        self._uow_factory = uow_factory
        self._assembler = assembler

    async def execute(self, query: FeedQuery) -> Result[Feed]:
        uow = self._uow_factory()
        async with uow:
            book = await uow.books.get(query.book_id)
            if book is None:
                return Err(errors.BookNotFound("That book isn't here."))

            posts = await uow.posts.list_for_book(query.book_id)
            return Ok(
                self._assembler.assemble(book, posts, query.viewer, query.post_type)
            )
