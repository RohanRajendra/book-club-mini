"""AddBook, UpdateBook, ListBooks."""

from __future__ import annotations

import pytest

from app.adapters.memory import InMemoryUnitOfWork
from unittest import mock

from app.application.use_cases import books as books_module
from app.application.use_cases.books import (
    STATUS_ORDER,
    AddBook,
    BookCommand,
    ListBooks,
    UpdateBook,
)
from app.domain import errors
from app.domain.entities import Book
from app.domain.values import BookId, BookStatus, Position
from tests.builders import ADA, make_post

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


class TestOnlyOneBookStaysCurrent:
    """`_pause_the_current_book` reads every book and then writes, so two
    concurrent "set currently reading" calls both read before either writes and
    both survive. The app offers no way to express two current books — the
    spine and the default book both assume one — so the state was unreachable
    by intent and unrepairable once reached.
    """

    async def setup_two_current(self, uow):
        """Reached through the store, because the use case refuses to create
        it. That is the point: the state arrives from a race or a hand-edit,
        never from the app."""
        async with uow:
            for title in ("Piranesi", "Jonathan Strange"):
                await uow.books.add(Book(title=title, status=READING))
            await uow.commit()

    async def test_the_extra_current_book_is_demoted(self, uow, listing):
        await self.setup_two_current(uow)
        books = (await listing.execute()).unwrap()
        current = [book for book in books if book.status is READING]
        assert len(current) == 1

    async def test_the_demotion_is_paused_not_finished(self, uow, listing):
        """Same reason `_pause_the_current_book` chooses Paused: the app cannot
        tell whether you finished a book or set it aside, and guessing writes a
        false claim into the owner's Notion."""
        await self.setup_two_current(uow)
        books = (await listing.execute()).unwrap()
        assert {book.status for book in books} == {READING, BookStatus.PAUSED}

    async def test_the_repair_is_written_not_just_displayed(self, uow, listing):
        """Notion is the source of truth and the owner reads it directly, so a
        repair that only changed what the app displayed would leave the app and
        the workspace disagreeing."""
        await self.setup_two_current(uow)
        await listing.execute()

        async with uow:
            stored = await uow.books.list_all()
        assert sum(book.status is READING for book in stored) == 1

    async def test_a_healthy_list_writes_nothing(self, uow, listing, add):
        """The common case must not turn a read into a write."""
        await add.execute(BookCommand(title="Piranesi", status=READING))
        await add.execute(BookCommand(title="Jonathan Strange"))
        async with uow:
            before = [book.status for book in await uow.books.list_all()]

        await listing.execute()

        async with uow:
            assert [book.status for book in await uow.books.list_all()] == before

    async def test_a_healthy_list_does_not_commit(self, uow, listing, add):
        """A commit fires the `on_commit` hooks, and feed-cache invalidation is
        one of them — so a read that commits anyway would clear the cache on
        every book list, which is most page loads."""
        await add.execute(BookCommand(title="Piranesi", status=READING))
        fired: list[int] = []
        uow.on_commit.append(lambda: fired.append(1))

        await listing.execute()

        assert fired == []

    async def test_a_repair_does_commit(self, uow, listing):
        """The other half: a repair is a write, and the feed cache holds
        spoiler flags computed against the book that was current."""
        await self.setup_two_current(uow)
        fired: list[int] = []
        uow.on_commit.append(lambda: fired.append(1))

        await listing.execute()

        assert fired == [1]

    async def test_one_current_book_is_left_alone(self, uow, listing, add):
        await add.execute(BookCommand(title="Piranesi", status=READING))
        books = (await listing.execute()).unwrap()
        assert [book.status for book in books] == [READING]

    async def test_no_current_book_is_left_alone(self, uow, listing, add):
        await add.execute(BookCommand(title="Piranesi", status=BookStatus.UPCOMING))
        books = (await listing.execute()).unwrap()
        assert [book.status for book in books] == [BookStatus.UPCOMING]


def test_every_status_has_a_place_in_the_ordering():
    """The book list sorts by status, and a status missing from the ordering
    used to raise — a 500 on `GET /api/books` the day a fifth is added. It now
    sorts last, and this is what makes adding one a failing test instead of a
    surprise in production."""
    assert set(STATUS_ORDER) == set(BookStatus)


async def test_a_status_outside_the_ordering_sorts_last_instead_of_raising(add, listing):
    """Reached by shortening STATUS_ORDER, not by editing Notion — the mapper
    maps an unknown Notion status to Upcoming. This is the runtime half of the
    guard above, and it stands in for the day a fifth status is added to the
    enum and not to the ordering."""
    for title, status in (("Zeta", BookStatus.FINISHED), ("Alpha", READING)):
        await add.execute(BookCommand(title=title, status=status))

    with (
        mock.patch.object(books_module, "STATUS_ORDER", [READING]),
        mock.patch.object(books_module, "_STATUS_RANK", {READING: 0}),
    ):
        titles = [book.title for book in (await listing.execute()).unwrap()]
    assert titles == ["Alpha", "Zeta"]


class TestBookTextFields:
    """A title or author too long for the store, and whitespace in either.

    An oversize value passed every layer and Notion rejected it, so a member
    who pasted the wrong thing into a text box was told "Can't reach Notion
    right now" — a 502 for a typing mistake.
    """

    #: The store's own cap on a title or rich text property, in UTF-16 units.
    OVER = "x" * 2001

    async def test_an_oversize_title_is_refused_with_a_readable_error(self, add):
        result = await add.execute(BookCommand(title=self.OVER))
        error = result.unwrap_err()
        assert isinstance(error, errors.TextTooLong)
        assert "title" in error.message and "2,000" in error.message

    async def test_a_title_at_exactly_the_limit_is_accepted(self, add):
        title = "x" * 2000
        assert (await add.execute(BookCommand(title=title))).unwrap().title == title

    async def test_an_oversize_author_is_refused(self, add):
        result = await add.execute(BookCommand(title="Piranesi", author=self.OVER))
        assert isinstance(result.unwrap_err(), errors.TextTooLong)

    async def test_the_limit_counts_utf16_units(self, add):
        """1001 emoji is 2002 units — over the cap at half the character
        count, and exactly what Notion refuses."""
        result = await add.execute(BookCommand(title="\U0001F600" * 1001))
        assert isinstance(result.unwrap_err(), errors.TextTooLong)

    async def test_an_oversize_title_is_refused_on_edit_too(self, add, update):
        book = (await add.execute(BookCommand(title="Piranesi"))).unwrap()
        result = await update.execute(book.id, BookCommand(title=self.OVER))
        assert isinstance(result.unwrap_err(), errors.TextTooLong)

    async def test_a_whitespace_author_is_stored_as_no_author(self, add):
        """Blank-but-present displayed as an empty author line and could not be
        removed, because clearing a field was itself broken (issue #1)."""
        book = (await add.execute(BookCommand(title="Piranesi", author="   "))).unwrap()
        assert book.author is None

    async def test_an_author_is_stripped(self, add):
        book = (
            await add.execute(BookCommand(title="Piranesi", author="  Susanna Clarke "))
        ).unwrap()
        assert book.author == "Susanna Clarke"

    async def test_an_author_is_stripped_on_edit_too(self, add, update):
        book = (await add.execute(BookCommand(title="Piranesi"))).unwrap()
        edited = (
            await update.execute(
                book.id, BookCommand(title="Piranesi", author=" Clarke ")
            )
        ).unwrap()
        assert edited.author == "Clarke"

    async def test_clearing_an_author_still_works(self, add, update):
        book = (
            await add.execute(BookCommand(title="Piranesi", author="Clarke"))
        ).unwrap()
        edited = (
            await update.execute(book.id, BookCommand(title="Piranesi", author=None))
        ).unwrap()
        assert edited.author is None


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


class TestLoweringTotalChapters:
    """The chapter bound is enforced on write, so it has to keep holding.

    Shortening a book is the one edit that can strand posts outside it.
    """

    @pytest.fixture
    async def book(self, uow, add):
        created = (
            await add.execute(BookCommand(title="Piranesi", total_chapters=45))
        ).unwrap()
        async with uow:
            await uow.posts.add(
                make_post(id=None, book_id=created.id, member=ADA, position=Position(30))
            )
            await uow.commit()
        return created

    async def test_lowering_below_an_existing_post_is_refused(self, update, book):
        result = await update.execute(
            book.id, BookCommand(title="Piranesi", total_chapters=20)
        )
        assert isinstance(result.unwrap_err(), errors.TotalChaptersBelowPosts)

    async def test_the_message_names_the_count_and_the_furthest_chapter(
        self, update, book
    ):
        message = (
            await update.execute(
                book.id, BookCommand(title="Piranesi", total_chapters=20)
            )
        ).unwrap_err().message
        assert "1 post is" in message
        assert "30" in message

    async def test_lowering_to_exactly_the_furthest_post_is_allowed(self, update, book):
        result = await update.execute(
            book.id, BookCommand(title="Piranesi", total_chapters=30)
        )
        assert result.unwrap().total_chapters == 30

    async def test_lowering_above_every_post_is_allowed(self, update, book):
        result = await update.execute(
            book.id, BookCommand(title="Piranesi", total_chapters=40)
        )
        assert result.unwrap().total_chapters == 40

    async def test_raising_the_total_is_always_allowed(self, update, book):
        result = await update.execute(
            book.id, BookCommand(title="Piranesi", total_chapters=90)
        )
        assert result.unwrap().total_chapters == 90

    async def test_the_book_is_unchanged_when_the_edit_is_refused(
        self, update, book, uow
    ):
        await update.execute(book.id, BookCommand(title="Piranesi", total_chapters=20))
        async with uow:
            assert (await uow.books.get(book.id)).total_chapters == 45

    async def test_posts_without_a_position_do_not_block_the_edit(self, uow, add, update):
        created = (
            await add.execute(BookCommand(title="Piranesi", total_chapters=45))
        ).unwrap()
        async with uow:
            await uow.posts.add(
                make_post(id=None, book_id=created.id, member=ADA, position=None)
            )
            await uow.commit()

        result = await update.execute(
            created.id, BookCommand(title="Piranesi", total_chapters=2)
        )
        assert result.unwrap().total_chapters == 2

    async def test_a_status_only_edit_does_not_query_the_posts(self, uow, book, update):
        """The scan costs a full Notion query. Changing status is by far the
        most common edit and must not pay for a rule it cannot break."""
        uow.posts.calls.clear()
        await update.execute(
            book.id, BookCommand(title="Piranesi", status=READING, total_chapters=45)
        )
        assert [name for name, _ in uow.posts.calls] == []

    async def test_clearing_the_total_is_allowed_and_does_not_query_the_posts(
        self, uow, book, update
    ):
        """A book that states no length cannot exclude anything, so clearing
        the total can never strand a post and must not pay for a scan."""
        uow.posts.calls.clear()
        result = await update.execute(
            book.id, BookCommand(title="Piranesi", total_chapters=None)
        )
        assert result.unwrap().total_chapters is None
        assert [name for name, _ in uow.posts.calls] == []

    async def test_lowering_does_query_the_posts(self, uow, book, update):
        """The negative test above is worthless if the call never happens."""
        uow.posts.calls.clear()
        await update.execute(
            book.id, BookCommand(title="Piranesi", total_chapters=20)
        )
        assert [name for name, _ in uow.posts.calls] == ["list_for_book"]
