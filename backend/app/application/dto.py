"""Data the application layer hands to the interface layer.

Plain frozen dataclasses, not Pydantic: the domain and application layers stay
framework-free, and `interface/schemas.py` converts these to response DTOs
explicitly, in one direction, in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities import Book, Post
from app.domain.values import MemberName, Position


@dataclass(frozen=True, slots=True)
class FeedPost:
    """A post with its viewer-specific flags and its replies already nested."""

    post: Post
    is_spoiler: bool
    is_own: bool
    replies: list["FeedPost"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Spine:
    max_chapter: int
    is_estimated: bool


@dataclass(frozen=True, slots=True)
class Feed:
    book: Book
    posts: list[FeedPost]
    #: One entry per roster member. None means "hasn't started" — the spine
    #: renders that as a state and cannot if the member is simply absent.
    positions: dict[MemberName, Position | None]
    spine: Spine
    #: Counts for all four filter chips, so the client can filter locally
    #: without losing the counts of the types it filtered out (spec-deltas D3).
    counts: dict[str, int]
