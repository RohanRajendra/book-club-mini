"""Application settings, loaded from backend/.env.

MEMBERS is the full roster and must contain MEMBER_NAME. An installation that is
not in its own roster renders a broken spine and attributes posts to a member the
app does not know about, so this fails at startup rather than at first render.

Roster *order* is significant: reader colours are assigned by index (01-ux-spec.md
§Visual direction), so both installations must list the members identically.
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

    @property
    def reader_index(self) -> int:
        """This member's position in the roster, which selects their colour."""
        return self.members.index(self.member_name)
