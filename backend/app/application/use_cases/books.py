"""Book use cases: list, add, update.

A title is the only required field. Author and total chapters are optional and
fillable later — the spine calibrates itself without them, and demanding a
chapter count means looking something up before you can use the app.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from app.domain import errors
from app.domain.entities import Book
from app.domain.result import Err, Ok, Result
from app.domain.values import BookId, BookStatus
from app.ports.unit_of_work import UnitOfWork

#: The order the book dropdown groups by. Notion cannot sort by select option
#: order, so this happens in Python.
STATUS_ORDER = [
    BookStatus.CURRENTLY_READING,
    BookStatus.UPCOMING,
    BookStatus.PAUSED,
    BookStatus.FINISHED,
]


@dataclass(frozen=True, slots=True)
class BookCommand:
    title: str
    author: str | None = None
    status: BookStatus = BookStatus.UPCOMING
    total_chapters: int | None = None


def _sort_key(book: Book) -> tuple[int, str]:
    return STATUS_ORDER.index(book.status), book.title.casefold()


async def _pause_the_current_book(uow: UnitOfWork, keeping: BookId | None) -> None:
    """Only one book is `Currently Reading`.

    The demoted book becomes Paused, not Finished: the app cannot tell whether
    you finished a book or set it aside, and guessing writes a false claim into
    the owner's Notion.
    """
    for other in await uow.books.list_all():
        if other.status is BookStatus.CURRENTLY_READING and other.id != keeping:
            await uow.books.update(replace(other, status=BookStatus.PAUSED))


class ListBooks:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> Result[list[Book]]:
        uow = self._uow_factory()
        async with uow:
            return Ok(sorted(await uow.books.list_all(), key=_sort_key))


class AddBook:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: BookCommand) -> Result[Book]:
        if not command.title.strip():
            return Err(errors.TitleRequired("A book needs a title."))

        uow = self._uow_factory()
        async with uow:
            if command.status is BookStatus.CURRENTLY_READING:
                await _pause_the_current_book(uow, keeping=None)

            created = await uow.books.add(
                Book(
                    title=command.title.strip(),
                    author=command.author,
                    status=command.status,
                    total_chapters=command.total_chapters,
                )
            )
            await uow.commit()
            return Ok(created)


class UpdateBook:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, book_id: BookId, command: BookCommand) -> Result[Book]:
        if not command.title.strip():
            return Err(errors.TitleRequired("A book needs a title."))

        uow = self._uow_factory()
        async with uow:
            existing = await uow.books.get(book_id)
            if existing is None:
                return Err(errors.BookNotFound("That book isn't here."))

            if command.status is BookStatus.CURRENTLY_READING:
                await _pause_the_current_book(uow, keeping=book_id)

            updated = await uow.books.update(
                replace(
                    existing,
                    title=command.title.strip(),
                    author=command.author,
                    status=command.status,
                    total_chapters=command.total_chapters,
                )
            )
            await uow.commit()
            return Ok(updated)
