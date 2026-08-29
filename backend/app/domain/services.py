"""Domain services: rules that operate over a collection rather than one entity."""

from __future__ import annotations

import math

from app.domain.entities import PREVIEW_LIMIT, Post
from app.domain.values import MemberName, Position, PostType

#: A Notion rich text array holds at most 100 objects of 2000 characters.
MAX_BODY = 200_000

#: Floor for an inferred spine scale. A known total gives the true scale, even
#: when it is smaller than this (01-ux-spec.md §Scale calibration).
MIN_SCALE = 10

#: Inferred scales get 20% headroom so the newest tick is not pinned to the edge.
HEADROOM = 1.2


class PositionResolver:
    """Each member's current position: their most recent Progress post."""

    def resolve(self, posts: list[Post]) -> dict[MemberName, Position]:
        """Latest, not highest.

        A member who mistypes chapter 40 for chapter 4 fixes it by posting
        again; highest-wins would strand them for the rest of the book.

        Notion timestamps have second resolution, so two progress posts can tie.
        On a tie the last one in input order wins — arbitrary, but deterministic,
        which is what stops the tests turning flaky.
        """
        latest: dict[MemberName, Post] = {}
        for post in posts:
            if post.type is not PostType.PROGRESS or post.created_at is None:
                continue
            current = latest.get(post.member)
            if current is None or post.created_at >= current.created_at:
                latest[post.member] = post
        return {
            member: post.position
            for member, post in latest.items()
            if post.position is not None
        }


class BodySplitter:
    """Split a body into the feed preview and the full text behind it."""

    def split(self, body: str) -> tuple[str, bool, str | None]:
        """Return `(preview, has_full_body, full_body)`.

        When the body is long, the preview and the full body **overlap** — the
        first 1900 characters exist in both places. That redundancy is
        intentional: storing only the remainder in the block would mean
        reassembling a body from two sources on every edit, which is exactly
        how posts get corrupted.
        """
        if len(body) > MAX_BODY:
            raise ValueError(
                f"body must be at most {MAX_BODY} characters, got {len(body)}"
            )
        if len(body) <= PREVIEW_LIMIT:
            return body, False, None

        head = body[:PREVIEW_LIMIT]
        cut = head.rfind(" ")
        preview = head[:cut].rstrip() if cut > 0 else head
        return preview, True, body


class ScaleCalculator:
    """How far the spine's track reaches, and whether that is a guess."""

    def calculate(
        self, total_chapters: int | None, observed_max: int | None
    ) -> tuple[int, bool]:
        """Return `(max_chapter, is_estimated)`.

        `is_estimated` tracks whether the book told us its length, not whether
        the number was adjusted. A stated total that a post overshoots is still
        not an estimate — the overshoot is a data error in Notion, and the
        spine's job is to stay honest about its source while still containing
        the post (docs/spec-deltas.md D6).
        """
        observed = observed_max or 0
        if total_chapters is not None:
            return max(total_chapters, observed), False
        return max(math.ceil(observed * HEADROOM), MIN_SCALE), True
