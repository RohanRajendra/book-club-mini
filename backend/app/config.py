"""Application settings, loaded from backend/.env, or from the environment.

MEMBERS is the full roster and must contain MEMBER_NAME. An installation that is
not in its own roster renders a broken spine and attributes posts to a member the
app does not know about, so this fails at startup rather than at first render.

Roster *order* is significant: reader colours are assigned by index, so both
installations must list the members identically.
"""

from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    notion_token: str
    notion_books_db_id: str
    notion_posts_db_id: str
    member_name: str

    # Resolving a database ID to its data source ID costs a Notion round trip
    # each, on every start. They never change, so a deployment that starts
    # often can supply them directly and skip the lookup. Both or neither:
    # half the pair would mean one resolved and one not, for no benefit.
    notion_books_data_source_id: str | None = None
    notion_posts_data_source_id: str | None = None

    # NoDecode stops pydantic-settings from JSON-decoding the raw env value, so
    # the comma-separated form in .env.example reaches the validator below.
    members: Annotated[list[str], NoDecode]

    @field_validator("members", mode="before")
    @classmethod
    def _split_roster(cls, value: object) -> list[str]:
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, (list, tuple)):
            raise ValueError("MEMBERS must be a comma-separated list of names")
        return [str(name).strip() for name in value if str(name).strip()]

    @field_validator("members")
    @classmethod
    def _roster_is_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("MEMBERS must name at least one member")
        return value

    @model_validator(mode="after")
    def _member_is_in_the_roster(self) -> "Settings":
        if self.member_name not in self.members:
            raise ValueError(
                f"MEMBER_NAME {self.member_name!r} is not in MEMBERS "
                f"{self.members!r}. Add it, or correct the spelling — an "
                f"installation missing from its own roster cannot render the spine."
            )
        return self

    @model_validator(mode="after")
    def _data_source_ids_come_as_a_pair(self) -> "Settings":
        supplied = [
            self.notion_books_data_source_id,
            self.notion_posts_data_source_id,
        ]
        if any(supplied) and not all(supplied):
            raise ValueError(
                "Supply both NOTION_BOOKS_DATA_SOURCE_ID and "
                "NOTION_POSTS_DATA_SOURCE_ID, or neither. One alone saves "
                "nothing and hides which half is stale."
            )
        return self

    @property
    def known_data_source_ids(self) -> tuple[str, str] | None:
        """The configured pair, or `None` when they must be resolved."""
        if self.notion_books_data_source_id and self.notion_posts_data_source_id:
            return (
                self.notion_books_data_source_id,
                self.notion_posts_data_source_id,
            )
        return None

    @property
    def reader_index(self) -> int:
        """This member's position in the roster, which selects their colour."""
        return self.members.index(self.member_name)
