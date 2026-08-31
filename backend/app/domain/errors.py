"""The expected-failure taxonomy.

These are values carried by `Err`, not exceptions — deliberately, so that raising
one is impossible and the only way to signal an expected failure is to return it.
Genuine faults (network, misconfiguration, bugs) stay as real exceptions.

`code` is what interface/errors.py maps to an HTTP status. An architecture test
asserts every subclass here appears in that table, because the default for an
unmapped error would be a silent 500.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class DomainError:
    """Base for every expected failure. `message` is shown to the member.

    No ``slots=True``: it rebuilds the class, which leaves the pre-slots
    original registered in ``__subclasses__()`` and makes
    ``all_domain_errors()`` report every error twice.
    """

    message: str

    #: Stable identifier for the HTTP error map. Never shown to a member.
    code: ClassVar[str] = ""


@dataclass(frozen=True)
class BookNotFound(DomainError):
    code: ClassVar[str] = "book_not_found"


@dataclass(frozen=True)
class PostNotFound(DomainError):
    code: ClassVar[str] = "post_not_found"


@dataclass(frozen=True)
class NotPostOwner(DomainError):
    code: ClassVar[str] = "not_post_owner"


@dataclass(frozen=True)
class CannotReplyToReply(DomainError):
    code: ClassVar[str] = "cannot_reply_to_reply"


@dataclass(frozen=True)
class ReplyBookMismatch(DomainError):
    code: ClassVar[str] = "reply_book_mismatch"


@dataclass(frozen=True)
class ChapterRequiredForProgress(DomainError):
    code: ClassVar[str] = "chapter_required_for_progress"


@dataclass(frozen=True)
class PageRequiresChapter(DomainError):
    code: ClassVar[str] = "page_requires_chapter"


@dataclass(frozen=True)
class ChapterBeyondBook(DomainError):
    code: ClassVar[str] = "chapter_beyond_book"


@dataclass(frozen=True)
class TotalChaptersBelowPosts(DomainError):
    code: ClassVar[str] = "total_chapters_below_posts"


@dataclass(frozen=True)
class SpoilerWithheld(DomainError):
    code: ClassVar[str] = "spoiler_withheld"


@dataclass(frozen=True)
class BodyRequired(DomainError):
    code: ClassVar[str] = "body_required"


@dataclass(frozen=True)
class BodyTooLong(DomainError):
    code: ClassVar[str] = "body_too_long"


@dataclass(frozen=True)
class TitleRequired(DomainError):
    code: ClassVar[str] = "title_required"


@dataclass(frozen=True)
class UnknownMember(DomainError):
    code: ClassVar[str] = "unknown_member"


def all_domain_errors() -> list[type[DomainError]]:
    """Every concrete subclass, for the uniqueness and mapping-coverage tests."""

    def descendants(cls: type[DomainError]) -> list[type[DomainError]]:
        found: list[type[DomainError]] = []
        for sub in cls.__subclasses__():
            found.append(sub)
            found.extend(descendants(sub))
        return found

    return descendants(DomainError)
