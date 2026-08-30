"""The spoiler rule, isolated as a Strategy.

It is the single most likely thing in this app to change, and isolating it means
a percent-based variant is a new class rather than an `if` inside this one
.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import Post
from app.domain.values import MemberName, Position


class SpoilerPolicy(ABC):
    @abstractmethod
    def is_spoiler(
        self,
        post: Post,
        viewer: MemberName,
        viewer_position: Position | None,
    ) -> bool:
        """Whether `post` should be blurred for `viewer`."""


class ChapterFirstSpoilerPolicy(SpoilerPolicy):
    """Chapter dominates; page is a tiebreaker within a chapter.

    The two members may hold different editions where page numbers do not
    correspond, or one may be listening on audio with no pages at all. Both
    pages must be present for the page comparison — inside a single chapter, a
    false blur is more irritating than a mild spoiler.
    """

    def is_spoiler(
        self,
        post: Post,
        viewer: MemberName,
        viewer_position: Position | None,
    ) -> bool:
        if post.member == viewer:
            return False
        if viewer_position is None:
            return False
        if post.position is None:
            return False
        return post.position.is_ahead_of(viewer_position)
