"""Application settings, loaded from backend/.env, or from the environment.

MEMBERS is the full roster. Its *order* is significant: reader colours are
assigned by index, so every installation must list the members identically.

AUTH_MODE decides where identity comes from, and the rest of the file follows
from it. Under `open` the app is one person's process and MEMBER_NAME says who
they are; a name outside its own roster renders a broken spine and attributes
posts to a member the app does not know about, so that fails at startup rather
than at first render. Under `passphrase` the app is shared, identity arrives per
request, and MEMBER_NAME means nothing.
"""

from enum import Enum
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AuthMode(str, Enum):
    """How the app decides who is asking.

    `open` is the original model and stays the default: identity is a
    configuration value and there is no login. That is right for a process on
    one person's machine, and it is what `./dev.sh` runs.

    `passphrase` is for a deployment both members reach. One shared secret
    keeps strangers out, and each browser says which member it is.
    """

    OPEN = "open"
    PASSPHRASE = "passphrase"


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
    auth_mode: AuthMode = AuthMode.OPEN

    #: Required under `open`, meaningless under `passphrase`.
    member_name: str | None = None

    #: Required under `passphrase`. The secret signs the session cookie; the
    #: hash is what a submitted passphrase is checked against. Neither the
    #: passphrase nor the secret is ever stored in the repository.
    session_secret: str | None = None
    site_passphrase_hash: str | None = None

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
    def _identity_is_settled(self) -> "Settings":
        if self.member_name is not None and self.member_name not in self.members:
            raise ValueError(
                f"MEMBER_NAME {self.member_name!r} is not in MEMBERS "
                f"{self.members!r}. Add it, or correct the spelling — an "
                f"installation missing from its own roster cannot render the spine."
            )
        if self.auth_mode is AuthMode.OPEN and self.member_name is None:
            raise ValueError(
                "MEMBER_NAME is required when AUTH_MODE is 'open'. With no "
                "login there is nothing else to identify this installation by."
            )
        if self.auth_mode is AuthMode.PASSPHRASE and not (
            self.session_secret and self.site_passphrase_hash
        ):
            raise ValueError(
                "AUTH_MODE 'passphrase' needs SESSION_SECRET and "
                "SITE_PASSPHRASE_HASH. Generate both with "
                "`python scripts/make_secrets.py`. Failing here beats a "
                "deployment that starts and lets anyone in."
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
        """This installation's position in the roster, which selects a colour.

        Only meaningful under `open`. Under `passphrase` the colour belongs to
        whoever is asking, so it is derived from the session — see
        `Container.reader_index`.
        """
        if self.member_name is None:
            raise ValueError("no MEMBER_NAME: identity comes from the session")
        return self.members.index(self.member_name)
