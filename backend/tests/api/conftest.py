"""API test wiring.

`httpx.ASGITransport` does not run ASGI lifespan events, so the container that
`main.py` builds in its lifespan handler never exists here. The fixture builds
one with in-memory adapters and attaches it directly.

That is exactly the capability the container exists to provide — the same seam
scripts use — so the tests are possible *because* of the composition root, not
in spite of it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.memory import in_memory_uow_factory
from app.composition import Container
from app.config import Settings
from app.domain.entities import Book
from app.domain.values import BookId
from app.main import create_app
from tests.builders import at_minute

SETTINGS = dict(
    notion_token="ntn_test",
    notion_books_db_id="books-db",
    notion_posts_db_id="posts-db",
    member_name="Ada",
    members="Ada,Grace",
)

BOOK = BookId("book-1")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, **SETTINGS)


@pytest.fixture
def uow_factory():
    return in_memory_uow_factory(clock=lambda: at_minute(0))


@pytest.fixture
def container(settings, uow_factory) -> Container:
    return Container(settings, uow_factory=uow_factory)


@pytest.fixture
async def seeded(uow_factory):
    uow = uow_factory()
    async with uow:
        await uow.books.add(Book(id=BOOK, title="Piranesi", total_chapters=30))
        await uow.commit()
    return uow_factory


@pytest.fixture
async def client(container, seeded):
    app = create_app()
    app.state.container = container
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
