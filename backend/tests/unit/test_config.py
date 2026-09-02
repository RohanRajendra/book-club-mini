"""Settings validation — the first red-green cycle of the project.

`test_settings_rejects_member_name_absent_from_members` is the one that matters:
an installation whose MEMBER_NAME is not in its own roster renders a broken spine
and attributes posts to a member the app does not know about. Fail at startup.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings

VALID = {
    "notion_token": "ntn_test",
    "notion_books_db_id": "books-db",
    "notion_posts_db_id": "posts-db",
    "member_name": "Ada",
    "members": "Ada,Grace",
}


def build(**overrides) -> Settings:
    """Construct Settings from explicit values, ignoring any real .env on disk."""
    return Settings(_env_file=None, **{**VALID, **overrides})


def test_settings_parses_members_into_list():
    assert build().members == ["Ada", "Grace"]


def test_settings_strips_whitespace_around_member_names():
    assert build(members="  Ada ,  Grace  ").members == ["Ada", "Grace"]


def test_settings_rejects_member_name_absent_from_members():
    with pytest.raises(ValidationError, match="MEMBER_NAME"):
        build(member_name="Alan")


def test_settings_rejects_empty_members():
    with pytest.raises(ValidationError):
        build(members="")


def test_settings_rejects_missing_notion_token():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            notion_books_db_id="books-db",
            notion_posts_db_id="posts-db",
            member_name="Ada",
            members="Ada,Grace",
        )


def test_settings_accepts_a_members_list_already_parsed():
    assert build(members=["Ada", "Grace"]).members == ["Ada", "Grace"]


def test_settings_drops_trailing_empty_entries_from_members():
    assert build(members="Ada,Grace,").members == ["Ada", "Grace"]


def test_settings_reader_index_is_the_roster_position():
    assert build(member_name="Grace").reader_index == 1


class TestKnownDataSourceIds:
    """Resolving a database ID to its data source costs a Notion round trip
    each. A long-lived process pays that once; a serverless one pays it on
    every cold start, which is most requests."""

    IDS = {
        "notion_books_data_source_id": "books-ds",
        "notion_posts_data_source_id": "posts-ds",
    }

    def test_absent_by_default_so_the_lookup_still_happens(self):
        assert build().known_data_source_ids is None

    def test_both_supplied_are_returned_as_a_pair(self):
        assert build(**self.IDS).known_data_source_ids == ("books-ds", "posts-ds")

    def test_one_alone_is_refused(self):
        """Half the pair means one resolved and one not, for no benefit, and
        hides which half is stale."""
        for key in self.IDS:
            with pytest.raises(ValidationError, match="both"):
                build(**{key: "only-one"})

    def test_an_empty_string_counts_as_absent(self):
        """A Vercel environment variable set to nothing is the shape this
        arrives in when someone clears it."""
        assert build(**{k: "" for k in self.IDS}).known_data_source_ids is None
