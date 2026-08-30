"""Mapper tests against **real** recorded Notion responses.

phase-4 §4.4: "Test these against the real fixtures from Phase 1.6, not
hand-written payloads." Hand-written approximations are how a suite goes green
against an API that would reject it, so these skip rather than substitute one.

See tests/fixtures/notion/README.md for how to capture them. The mappers are
not untested in the meantime: the contract suite round-trips every entity
through `to_properties` → stub → `to_domain` for both adapters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.notion.mappers import BookMapper, PostMapper
from app.domain.values import BookStatus, PostType

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "notion"

MISSING = (
    "Real Notion fixtures are not captured yet. They need a live workspace — "
    "see tests/fixtures/notion/README.md and docs/notion-setup.md."
)


def load(name: str) -> dict:
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"{MISSING} (missing {name})")
    return json.loads(path.read_text(encoding="utf-8"))


def rows(name: str = "query.json") -> list[dict]:
    return load(name)["results"]


def find_row(predicate) -> dict:
    matching = [row for row in rows() if predicate(row)]
    if not matching:
        pytest.skip(f"{MISSING} (no matching row in query.json)")
    return matching[0]


def has_property(row: dict, name: str) -> bool:
    return name in row.get("properties", {})


def rows_with_type() -> list[dict]:
    matching = [row for row in rows() if has_property(row, "Type")]
    if len(matching) < 2:
        pytest.skip(f"{MISSING} (query.json needs at least two posts)")
    return matching


class TestBookMapper:
    def test_a_real_book_row_maps_to_a_book(self):
        book = BookMapper().to_domain(load("page_create.json"))
        assert book.title
        assert book.id is not None

    def test_unknown_status_maps_to_upcoming(self):
        page = load("page_create.json")
        page["properties"]["Status"] = {"select": {"name": "Abandoned mid-chapter"}}
        assert BookMapper().to_domain(page).status is BookStatus.UPCOMING

    def test_missing_author_maps_to_none(self):
        page = load("page_create.json")
        page["properties"].pop("Author", None)
        assert BookMapper().to_domain(page).author is None

    def test_missing_total_chapters_maps_to_none(self):
        page = load("page_create.json")
        page["properties"].pop("Total Chapters", None)
        assert BookMapper().to_domain(page).total_chapters is None

    def test_to_properties_omits_none_valued_fields(self):
        from app.domain.entities import Book

        properties = BookMapper().to_properties(Book(title="Piranesi"))
        assert "Author" not in properties
        assert "Total Chapters" not in properties


class TestPostMapper:
    def test_a_real_post_row_maps_to_a_post(self):
        post = PostMapper().to_domain(find_row(lambda row: has_property(row, "Type")))
        assert post.id is not None
        assert isinstance(post.type, PostType)

    def test_a_real_select_value_maps_to_its_enum_member(self):
        """Guards the fixtures themselves.

        An over-eager scrubber once replaced every select `name` with
        "scrubbed"; the mapper fell back to Thought and every shape assertion
        still passed. Asserting a *recognised* value is what catches that.
        """
        rows = [PostMapper().to_domain(row) for row in rows_with_type()]
        assert {post.type for post in rows} == {PostType.THOUGHT, PostType.REPLY}
        assert all(post.member.value != "scrubbed" for post in rows)

    def test_a_real_reply_row_carries_its_parent_and_copied_position(self):
        reply = find_row(
            lambda row: row["properties"].get("Parent Post ID", {}).get("rich_text")
        )
        post = PostMapper().to_domain(reply)
        assert post.type is PostType.REPLY
        assert post.parent_post_id is not None
        assert post.position is not None

    def test_a_real_long_post_reports_has_full_body(self):
        row = find_row(
            lambda row: row["properties"].get("Has Full Body", {}).get("checkbox")
        )
        assert PostMapper().to_domain(row).has_full_body is True

    def test_created_and_edited_times_come_from_the_page_object(self):
        row = find_row(lambda row: "created_time" in row)
        post = PostMapper().to_domain(row)
        assert post.created_at is not None
        assert post.edited_at is not None

    def test_book_relation_maps_to_book_id(self):
        row = find_row(lambda row: row["properties"].get("Book", {}).get("relation"))
        post = PostMapper().to_domain(row)
        assert post.book_id.value == row["properties"]["Book"]["relation"][0]["id"]

    def test_empty_parent_post_id_maps_to_none(self):
        row = find_row(lambda row: not row["properties"].get("Parent Post ID", {}).get("rich_text"))
        assert PostMapper().to_domain(row).parent_post_id is None

    def test_post_with_no_chapter_maps_to_no_position(self):
        row = find_row(lambda row: has_property(row, "Chapter"))
        row["properties"]["Chapter"] = {"number": None}
        row["properties"]["Type"] = {"select": {"name": "Thought"}}
        assert PostMapper().to_domain(row).position is None

    def test_a_hand_edited_unknown_type_falls_back_to_thought(self):
        row = find_row(lambda row: has_property(row, "Type"))
        row["properties"]["Type"] = {"select": {"name": "Musing"}}
        row["properties"]["Parent Post ID"] = {"rich_text": []}
        assert PostMapper().to_domain(row).type is PostType.THOUGHT


class TestDataSourceShape:
    def test_the_database_response_exposes_data_sources(self):
        """The 2025-09-03 shape this whole adapter depends on."""
        database = load("database.json")
        assert database["data_sources"]
        assert "id" in database["data_sources"][0]

    def test_the_data_source_response_lists_the_expected_properties(self):
        properties = load("data_source.json")["properties"]
        assert "Title" in properties or "Name" in properties

    def test_block_children_carry_paragraph_rich_text(self):
        blocks = load("block_children.json")["results"]
        paragraphs = [block for block in blocks if block.get("type") == "paragraph"]
        if not paragraphs:
            pytest.skip(f"{MISSING} (no paragraph block in block_children.json)")
        assert "rich_text" in paragraphs[0]["paragraph"]
