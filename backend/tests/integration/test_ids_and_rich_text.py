from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.notion.http import BASE_URL, NotionHttpClient
from app.adapters.notion.ids import DataSourceResolver
from app.adapters.notion.rich_text import (
    CHUNK_SIZE,
    MAX_CONTENT,
    checkbox,
    from_rich_text,
    number,
    plain,
    relation_ids,
    select_name,
    to_rich_text,
)


@pytest.fixture
def client():
    return NotionHttpClient(token="t", client=httpx.AsyncClient(base_url=BASE_URL))


def database(*data_sources) -> dict:
    return {
        "object": "database",
        "id": "db",
        "data_sources": [{"id": ds, "name": ds} for ds in data_sources],
    }


class TestDataSourceResolver:
    @respx.mock
    async def test_resolves_first_data_source_id(self, client):
        respx.get(f"{BASE_URL}/databases/db").mock(
            return_value=httpx.Response(200, json=database("ds-1"))
        )
        assert await DataSourceResolver(client).resolve("db") == "ds-1"

    @respx.mock
    async def test_result_is_memoised_and_does_not_refetch(self, client):
        route = respx.get(f"{BASE_URL}/databases/db").mock(
            return_value=httpx.Response(200, json=database("ds-1"))
        )
        resolver = DataSourceResolver(client)
        await resolver.resolve("db")
        await resolver.resolve("db")
        assert route.call_count == 1

    @respx.mock
    async def test_warns_when_multiple_data_sources_present(self, client, caplog):
        respx.get(f"{BASE_URL}/databases/db").mock(
            return_value=httpx.Response(200, json=database("ds-1", "ds-2"))
        )
        with caplog.at_level("WARNING"):
            assert await DataSourceResolver(client).resolve("db") == "ds-1"
        assert "2 data sources" in caplog.text

    @respx.mock
    async def test_raises_a_readable_error_when_data_sources_is_empty(self, client):
        respx.get(f"{BASE_URL}/databases/db").mock(
            return_value=httpx.Response(200, json=database())
        )
        with pytest.raises(ValueError, match="no data sources"):
            await DataSourceResolver(client).resolve("db")

    @respx.mock
    async def test_two_databases_are_cached_separately(self, client):
        respx.get(f"{BASE_URL}/databases/a").mock(
            return_value=httpx.Response(200, json=database("ds-a"))
        )
        respx.get(f"{BASE_URL}/databases/b").mock(
            return_value=httpx.Response(200, json=database("ds-b"))
        )
        resolver = DataSourceResolver(client)
        assert await resolver.resolve("a") == "ds-a"
        assert await resolver.resolve("b") == "ds-b"


class TestRichText:
    def test_short_content_becomes_one_rich_text_object(self):
        assert to_rich_text("hello") == [
            {"type": "text", "text": {"content": "hello"}}
        ]

    def test_content_over_2000_chars_is_chunked(self):
        chunks = to_rich_text("x" * (CHUNK_SIZE + 1))
        assert len(chunks) == 2
        assert len(chunks[0]["text"]["content"]) == CHUNK_SIZE

    def test_chunk_boundaries_lose_no_characters(self):
        content = "".join(str(index % 10) for index in range(CHUNK_SIZE * 3 + 7))
        rebuilt = "".join(chunk["text"]["content"] for chunk in to_rich_text(content))
        assert rebuilt == content

    def test_content_over_200000_chars_raises(self):
        with pytest.raises(ValueError):
            to_rich_text("x" * (MAX_CONTENT + 1))

    def test_content_at_exactly_the_ceiling_is_accepted(self):
        assert len(to_rich_text("x" * MAX_CONTENT)) == 100

    def test_from_rich_text_round_trips_to_rich_text(self):
        """Chunking that drops a character at a boundary is invisible until
        someone loses a paragraph."""
        content = "The house is the world. " * 500
        assert from_rich_text(to_rich_text(content)) == content

    def test_empty_content_becomes_an_empty_array(self):
        assert to_rich_text("") == []
        assert from_rich_text([]) == ""
        assert from_rich_text(None) == ""

    def test_from_rich_text_prefers_plain_text_when_present(self):
        assert from_rich_text([{"plain_text": "a", "text": {"content": "b"}}]) == "a"


class TestReaders:
    PROPERTIES = {
        "Body Preview": {"rich_text": [{"plain_text": "hello"}]},
        "Chapter": {"number": 9},
        "Has Full Body": {"checkbox": True},
        "Status": {"select": {"name": "Paused"}},
        "Book": {"relation": [{"id": "book-1"}]},
        "Empty Select": {"select": None},
    }

    def test_readers_return_values_for_present_properties(self):
        assert plain(self.PROPERTIES, "Body Preview") == "hello"
        assert number(self.PROPERTIES, "Chapter") == 9
        assert checkbox(self.PROPERTIES, "Has Full Body") is True
        assert select_name(self.PROPERTIES, "Status") == "Paused"
        assert relation_ids(self.PROPERTIES, "Book") == ["book-1"]

    def test_readers_return_none_for_missing_properties(self):
        """The owner edits these rows by hand, and a hand-edit must not 500."""
        assert plain({}, "Body Preview") == ""
        assert number({}, "Chapter") is None
        assert checkbox({}, "Has Full Body") is False
        assert select_name({}, "Status") is None
        assert relation_ids({}, "Book") == []

    def test_an_emptied_select_reads_as_none(self):
        assert select_name(self.PROPERTIES, "Empty Select") is None

    def test_number_truncates_a_hand_typed_decimal(self):
        assert number({"Chapter": {"number": 9.0}}, "Chapter") == 9
