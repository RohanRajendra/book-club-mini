"""AddBook, UpdateBook, ListBooks."""

from __future__ import annotations

import pytest

from app.adapters.memory import InMemoryUnitOfWork
from app.application.use_cases.books import AddBook, BookCommand, ListBooks, UpdateBook
from app.domain import errors
from app.domain.entities import Book
from app.domain.values import BookId, BookStatus

READING = BookStatus.CURRENTLY_READING


@pytest.fixture
def uow():
    return InMemoryUnitOfWork()


@pytest.fixture
def add(uow):
    return AddBook(uow_factory=lambda: uow)


@pytest.fixture
def update(uow):
    return UpdateBook(uow_factory=lambda: uow)


@pytest.fixture
def listing(uow):
    return ListBooks(uow_factory=lambda: uow)


async def test_add_book_requires_a_title(add):
    result = await add.execute(BookCommand(title="   "))
    assert isinstance(result.unwrap_err(), errors.TitleRequired)


async def test_add_book_defaults_status_to_upcoming(add):
    assert (await add.execute(BookCommand(title="Piranesi"))).unwrap().status is (
        BookStatus.UPCOMING
    )


async def test_add_book_accepts_a_title_alone(add):
    """Author and total chapters are fillable later — demanding a chapter
    count means looking something up before you can use the app."""
    book = (await add.execute(BookCommand(title="Piranesi"))).unwrap()
    assert (book.author, book.total_chapters) == (None, None)


async def test_add_book_trims_the_title(add):
    assert (await add.execute(BookCommand(title="  Piranesi "))).unwrap().title == (
        "Piranesi"
    )


async def test_setting_a_book_current_pauses_the_previously_current_book(add, uow):
    first = (await add.execute(BookCommand(title="Piranesi", status=READING))).unwrap()
    await add.execute(BookCommand(title="Jonathan Strange", status=READING))

    async with uow:
        assert (await uow.books.get(first.id)).status is BookStatus.PAUSED


async def test_the_demoted_book_becomes_paused_not_finished(add, uow):
    """The app cannot tell whether you finished a book or set it aside, and
    guessing writes a false claim into the owner's Notion."""
    first = (await add.execute(BookCommand(title="Piranesi", status=READING))).unwrap()
    await add.execute(BookCommand(title="Jonathan Strange", status=READING))

    async with uow:
        assert (await uow.books.get(first.id)).status is not BookStatus.FINISHED


async def test_setting_a_book_current_when_none_was_current_pauses_nothing(add, uow):
    upcoming = (await add.execute(BookCommand(title="Piranesi"))).unwrap()
    await add.execute(BookCommand(title="Jonathan Strange", status=READING))

    async with uow:
        assert (await uow.books.get(upcoming.id)).status is BookStatus.UPCOMING


async def test_updating_an_unrelated_field_does_not_disturb_the_current_book(
    add, update, uow
):
    current = (await add.execute(BookCommand(title="Piranesi", status=READING))).unwrap()
    other = (await add.execute(BookCommand(title="Jonathan Strange"))).unwrap()

    await update.execute(
        other.id, BookCommand(title="Jonathan Strange", author="Susanna Clarke")
    )

    async with uow:
        assert (await uow.books.get(current.id)).status is READING


async def test_update_keeps_the_current_book_current_when_re_saved(add, update, uow):
    """Setting the already-current book current again must not pause itself."""
    current = (await add.execute(BookCommand(title="Piranesi", status=READING))).unwrap()
    await update.execute(current.id, BookCommand(title="Piranesi", status=READING))

    async with uow:
        assert (await uow.books.get(current.id)).status is READING


async def test_update_requires_a_title(update, add):
    book = (await add.execute(BookCommand(title="Piranesi"))).unwrap()
    result = await update.execute(book.id, BookCommand(title=""))
    assert isinstance(result.unwrap_err(), errors.TitleRequired)


async def test_update_of_an_unknown_book_returns_book_not_found(update):
    result = await update.execute(BookId("nope"), BookCommand(title="Ghost"))
    assert isinstance(result.unwrap_err(), errors.BookNotFound)


async def test_filling_in_the_chapter_count_later_is_allowed(add, update):
    book = (await add.execute(BookCommand(title="Piranesi"))).unwrap()
    result = await update.execute(
        book.id, BookCommand(title="Piranesi", total_chapters=30)
    )
    assert result.unwrap().total_chapters == 30


async def test_list_books_orders_currently_reading_then_upcoming_then_paused_then_finished(
    listing, uow
):
    async with uow:
        for title, status in [
            ("Finished book", BookStatus.FINISHED),
            ("Paused book", BookStatus.PAUSED),
            ("Upcoming book", BookStatus.UPCOMING),
            ("Reading book", READING),
        ]:
            await uow.books.add(Book(title=title, status=status))
        await uow.commit()

    titles = [book.title for book in (await listing.execute()).unwrap()]
    assert titles == ["Reading book", "Upcoming book", "Paused book", "Finished book"]


async def test_list_books_orders_alphabetically_within_a_status_group(listing, uow):
    async with uow:
        for title in ["Zeno", "amber", "Борис", "Middlemarch"]:
            await uow.books.add(Book(title=title, status=BookStatus.UPCOMING))
        await uow.commit()

    titles = [book.title for book in (await listing.execute()).unwrap()]
    assert titles[:3] == ["amber", "Middlemarch", "Zeno"]


async def test_list_books_on_an_empty_store_returns_an_empty_list(listing):
    assert (await listing.execute()).unwrap() == []
