"""Book use cases: list, add, update.

A title is the only required field. Author and total chapters are optional and
fillable later — the spine calibrates itself without them, and demanding a
chapter count means looking something up before you can use the app.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, replace
from typing import Callable

from app.application.position_rules import total_below_posts
from app.domain import errors
from app.domain.entities import FIELD_LIMIT, Book
from app.domain.result import Err, Ok, Result
from app.domain.text import utf16_length
from app.domain.values import BookId, BookStatus
from app.ports.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)

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


def _clean(value: str | None) -> str | None:
    """Strip a text field, and treat whitespace-only as absent.

    A whitespace author displayed as a blank-but-present line and, until
    clearing a field worked at all, could not be removed. Absent and
    blank should not be two different states.
    """
    if value is None:
        return None
    return value.strip() or None


def _too_long(command: BookCommand) -> errors.TextTooLong | None:
    """Refused here rather than by the store.

    Notion rejects an oversize property with a 400, which surfaces as "Can't
    reach Notion right now" — a 502 for a typing mistake, and no clue which
    field was at fault.
    """
    for name, value in (("title", command.title), ("author", command.author)):
        if value is None:
            continue
        length = utf16_length(value)
        if length > FIELD_LIMIT:
            return errors.TextTooLong(
                f"That {name} is {length:,} characters. The limit is "
                f"{FIELD_LIMIT:,}."
            )
    return None


#: Position in STATUS_ORDER, by status. A status missing from the ordering
#: sorts last rather than raising: a 500 on the whole book list is a poor way
#: to find out that a fifth status was added. The completeness test in
#: tests/unit/application/test_books.py is what actually catches that.
_STATUS_RANK = {status: rank for rank, status in enumerate(STATUS_ORDER)}


def _sort_key(book: Book) -> tuple[int, str]:
    return _STATUS_RANK.get(book.status, len(STATUS_ORDER)), book.title.casefold()


async def _posts_beyond(
    uow: UnitOfWork, book_id: BookId, total_chapters: int
) -> tuple[int, int]:
    """`(count, highest chapter)` for posts that a new total would exclude."""
    chapters = [
        post.position.chapter
        for post in await uow.posts.list_for_book(book_id)
        if post.position is not None and post.position.chapter > total_chapters
    ]
    return len(chapters), max(chapters, default=0)


def _tightens(new_total: int | None, old_total: int | None) -> bool:
    """Whether a change to `total_chapters` could strand an existing post.

    Guards the scan above, which costs a full post query. Raising the total,
    clearing it, or leaving it alone can never exclude anything, so a
    status-only edit — by far the most common — pays nothing.
    """
    if new_total is None:
        return False
    return old_total is None or new_total < old_total


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
    """Lists books, and repairs the one invariant a race can break.

    `_pause_the_current_book` reads every book and then writes, so two
    concurrent "set currently reading" calls both read before either writes and
    both survive. The app offers no way to *express* two current books — the
    spine and the default book each assume one — so the state is unreachable by
    intent and, until now, unrepairable once reached.

    The repair writes rather than only adjusting what is displayed. Notion is
    the source of truth and the owner reads it directly, so an app that quietly
    showed one current book while the workspace held two would be the worse
    failure. A healthy list writes nothing.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> Result[list[Book]]:
        uow = self._uow_factory()
        async with uow:
            books = sorted(await uow.books.list_all(), key=_sort_key)
            current = [
                book for book in books
                if book.status is BookStatus.CURRENTLY_READING
            ]
            if len(current) <= 1:
                return Ok(books)

            # Which one stays is arbitrary — nothing recorded says which was
            # set most recently — so it is the one the member already sees
            # first. Restoring the invariant is what matters; re-picking is one
            # click. Paused for the same reason the write path pauses: the app
            # cannot tell whether a book was finished or set aside.
            logger.warning(
                "%d books were Currently Reading; keeping %r and pausing the rest",
                len(current),
                current[0].title,
            )
            demoted = {
                book.id: replace(book, status=BookStatus.PAUSED)
                for book in current[1:]
            }
            for book in demoted.values():
                await uow.books.update(book)
            await uow.commit()

            return Ok(
                sorted(
                    (demoted.get(book.id, book) for book in books), key=_sort_key
                )
            )


class AddBook:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: BookCommand) -> Result[Book]:
        if not command.title.strip():
            return Err(errors.TitleRequired("A book needs a title."))
        too_long = _too_long(command)
        if too_long is not None:
            return Err(too_long)

        uow = self._uow_factory()
        async with uow:
            if command.status is BookStatus.CURRENTLY_READING:
                await _pause_the_current_book(uow, keeping=None)

            created = await uow.books.add(
                Book(
                    title=command.title.strip(),
                    author=_clean(command.author),
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
        too_long = _too_long(command)
        if too_long is not None:
            return Err(too_long)

        uow = self._uow_factory()
        async with uow:
            existing = await uow.books.get(book_id)
            if existing is None:
                return Err(errors.BookNotFound("That book isn't here."))

            # Shortening a book cannot be allowed to strand posts outside it:
            # the bound is enforced on write, so it has to hold afterwards too.
            if _tightens(command.total_chapters, existing.total_chapters):
                count, highest = await _posts_beyond(
                    uow, book_id, command.total_chapters
                )
                if count:
                    return Err(
                        total_below_posts(command.total_chapters, highest, count)
                    )

            if command.status is BookStatus.CURRENTLY_READING:
                await _pause_the_current_book(uow, keeping=book_id)

            updated = await uow.books.update(
                replace(
                    existing,
                    title=command.title.strip(),
                    author=_clean(command.author),
                    status=command.status,
                    total_chapters=command.total_chapters,
                )
            )
            await uow.commit()
            return Ok(updated)
