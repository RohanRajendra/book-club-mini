"""The composition root.

`test_a_test_container_can_be_built_with_in_memory_adapters_and_no_http` is the
container's real job. `Depends` alone would cover HTTP; tests and scripts need
the graph too.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.memory import InMemoryUnitOfWork, in_memory_uow_factory
from app.adapters.notion.http import BASE_URL
from app.adapters.notion.unit_of_work import NotionUnitOfWork
from app.application.caching import CachingFeedQuery
from app.composition import Container
from app.config import Settings
from tests.api.conftest import SETTINGS

ACCESSORS = [
    "list_books",
    "add_book",
    "update_book",
    "get_feed",
    "create_post",
    "edit_post",
    "delete_post",
    "get_post_body",
]


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, **SETTINGS)


def database(data_source: str) -> dict:
    return {"object": "database", "id": "db", "data_sources": [{"id": data_source}]}


@pytest.mark.parametrize("accessor", ACCESSORS)
def test_container_builds_every_use_case(settings, accessor):
    container = Container(settings, uow_factory=in_memory_uow_factory())
    assert getattr(container, accessor)() is not None


def test_a_test_container_can_be_built_with_in_memory_adapters_and_no_http(settings):
    container = Container(settings, uow_factory=in_memory_uow_factory())
    assert isinstance(container.uow_factory()(), InMemoryUnitOfWork)


async def test_startup_is_a_no_op_for_a_test_container(settings):
    """No HTTP client is built, so no network is reachable from these tests."""
    container = Container(settings, uow_factory=in_memory_uow_factory())
    await container.startup()
    await container.shutdown()
    assert container.books_data_source_id is None


@respx.mock
async def test_container_resolves_data_source_ids_once_on_startup(settings):
    books = respx.get(f"{BASE_URL}/databases/books-db").mock(
        return_value=httpx.Response(200, json=database("books-ds"))
    )
    posts = respx.get(f"{BASE_URL}/databases/posts-db").mock(
        return_value=httpx.Response(200, json=database("posts-ds"))
    )

    container = Container(settings)
    await container.startup()
    try:
        assert container.books_data_source_id == "books-ds"
        assert container.posts_data_source_id == "posts-ds"
        assert (books.call_count, posts.call_count) == (1, 1)
        assert isinstance(container.uow_factory()(), NotionUnitOfWork)
    finally:
        await container.shutdown()


@respx.mock
async def test_container_shutdown_closes_the_http_client(settings):
    respx.get(url__startswith=f"{BASE_URL}/databases/").mock(
        return_value=httpx.Response(200, json=database("ds"))
    )
    container = Container(settings)
    await container.startup()
    client = container._client
    await container.shutdown()

    assert client._client.is_closed
    assert container._client is None


def test_building_a_notion_uow_before_startup_is_a_readable_error(settings):
    container = Container(settings)
    with pytest.raises(RuntimeError, match="startup"):
        container.uow_factory()()


def test_the_feed_cache_is_a_singleton(settings):
    """One cache, or invalidation reaches an instance nobody reads from."""
    container = Container(settings, uow_factory=in_memory_uow_factory())
    assert container.get_feed() is container.get_feed()
    assert isinstance(container.get_feed(), CachingFeedQuery)


def test_every_unit_of_work_invalidates_the_cache_on_commit(settings):
    container = Container(settings, uow_factory=in_memory_uow_factory())
    uow = container.uow_factory()()
    assert container.get_feed().invalidate in uow.on_commit


def test_the_roster_and_member_come_from_settings(settings):
    container = Container(settings, uow_factory=in_memory_uow_factory())
    assert [name.value for name in container.roster] == ["Ada", "Grace"]
    assert container.member.value == "Ada"
