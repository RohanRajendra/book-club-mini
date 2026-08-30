"""Value objects: identifiers, post types, and reading position."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PostType(str, Enum):
    """The four kinds of post. Values are written into Notion's `Type` select
    verbatim, so they are capitalised the way the select options are."""

    PROGRESS = "Progress"
    THOUGHT = "Thought"
    QUESTION = "Question"
    REPLY = "Reply"


class BookStatus(str, Enum):
    """Values match Notion's `Status` select options verbatim."""

    CURRENTLY_READING = "Currently Reading"
    UPCOMING = "Upcoming"
    PAUSED = "Paused"
    FINISHED = "Finished"


@dataclass(frozen=True, slots=True)
class _Identifier:
    """A string identifier that will not silently substitute for another kind.

    Distinct subclasses never compare equal, so passing a book id where a post
    id belongs fails at the boundary — at runtime, since the project runs no
    type checker.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError(f"{type(self).__name__} cannot be empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MemberName(_Identifier):
    pass


@dataclass(frozen=True, slots=True)
class BookId(_Identifier):
    pass


@dataclass(frozen=True, slots=True)
class PostId(_Identifier):
    pass


@dataclass(frozen=True, slots=True)
class Position:
    """Where a member is in a book. Chapter is required, page is a tiebreaker."""

    chapter: int
    page: int | None = None

    def __post_init__(self) -> None:
        if self.chapter < 1:
            raise ValueError(f"chapter must be 1 or greater, got {self.chapter}")
        if self.page is not None and self.page < 1:
            raise ValueError(f"page must be 1 or greater, got {self.page}")

    def is_ahead_of(self, other: "Position") -> bool:
        """True when this position is strictly further into the book.

        Deliberately not `__lt__`. Two positions in the same chapter with one
        page missing are genuinely incomparable — one member may be reading an
        audiobook — and a comparison operator would have to invent an answer.
        This returns False for "cannot tell", which is honest, and it is the
        safe direction: inside a single chapter a false blur is more irritating
        than a mild spoiler.
        """
        if self.chapter != other.chapter:
            return self.chapter > other.chapter
        if self.page is None or other.page is None:
            return False
        return self.page > other.page
