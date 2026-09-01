"""Domain services: rules that operate over a collection rather than one entity."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from app.domain.entities import PREVIEW_LIMIT, Post
from app.domain.text import clip_to_utf16, utf16_length
from app.domain.values import MemberName, Position, PostType

#: What a Notion rich text array can be relied on to hold: 100 objects of 2000
#: UTF-16 code units, less one unit per object. An object closes a unit short
#: whenever the next character is astral and one unit of budget remains, and a
#: body can be built where that happens at every boundary. Measured in units,
#: like every other limit here — see domain/text.py.
#:
#: A test pins this equal to the adapter's own ceiling; the domain cannot
#: import it.
MAX_BODY = 199_900

#: Floor for an inferred spine scale. A known total gives the true scale, even
#: when it is smaller than this.
MIN_SCALE = 10

#: Inferred scales get 20% headroom so the newest tick is not pinned to the edge.
HEADROOM = 1.2

#: The shortest preview a word boundary may leave behind. Below this the text
#: is space-sparse — a URL after a one-word lead-in, base64, unspaced CJK — and
#: honouring the boundary would discard most of the preview to save one
#: mid-word cut. Four fifths of the budget: a trailing token up to 380
#: characters is still dropped whole.
MIN_PREVIEW = PREVIEW_LIMIT * 4 // 5

#: The last run of whitespace in a string, wherever it falls. `rfind(" ")`
#: would miss a body that breaks by line rather than by space.
_LAST_BOUNDARY = re.compile(r"\s\S*\Z")


#: Where a post with no timestamp sorts. The store assigns `created_at`, so an
#: absent one means a record that was never saved or was hand-edited into that
#: state — not news either way, so it sorts oldest.
_UNDATED = datetime(1, 1, 1, tzinfo=timezone.utc)


def created_order(post: Post) -> datetime:
    """A total ordering key for a post's creation time.

    `sorted` raises on the first pair it cannot compare, so one post with no
    timestamp — or one naive datetime among aware ones — is not a post that
    renders oddly. It is a 500 for the whole book. Notion always sends an
    offset, so a naive value means a hand-edited row or a future adapter, and
    neither should be able to take a feed down.
    """
    if post.created_at is None:
        return _UNDATED
    if post.created_at.tzinfo is None:
        return post.created_at.replace(tzinfo=timezone.utc)
    return post.created_at


class PositionResolver:
    """Each member's current position: their most recent Progress post."""

    def resolve(self, posts: list[Post]) -> dict[MemberName, Position]:
        """Latest, not highest.

        A member who mistypes chapter 40 for chapter 4 fixes it by posting
        again; highest-wins would strand them for the rest of the book.

        Ties are ordinary here, not exotic. Notion truncates `created_time` to
        the **minute** — every page in a live workspace reports `:00.000Z` — so
        a correction posted seconds after the mistake carries the same
        timestamp. Correcting a chapter within a minute is precisely the
        workflow this exists for, which makes the tie-break load-bearing.

        With the timestamps equal there is no signal left but input order, and
        `list_for_book` is contractually newest-first, ties included. So the
        **first** matching post wins. Keeping the last one meant keeping the
        mistake.
        """
        latest: dict[MemberName, Post] = {}
        for post in posts:
            if post.type is not PostType.PROGRESS or post.created_at is None:
                continue
            current = latest.get(post.member)
            if current is None or created_order(post) > created_order(current):
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

        The cut prefers a word boundary, but not at any price: see
        `MIN_PREVIEW`.
        """
        length = utf16_length(body)
        if length > MAX_BODY:
            raise ValueError(
                f"body must be at most {MAX_BODY} characters, got {length}"
            )
        if length <= PREVIEW_LIMIT:
            return body, False, None

        head = clip_to_utf16(body, PREVIEW_LIMIT)
        boundary = _LAST_BOUNDARY.search(head)
        if boundary is not None:
            preview = head[: boundary.start()].rstrip()
            if utf16_length(preview) >= MIN_PREVIEW:
                return preview, True, body
        # No boundary, or one so early that respecting it would throw most of
        # the preview away. A clean cut is worth a few characters, not a
        # thousand, so the limit wins and the word is split.
        return head, True, body


class ScaleCalculator:
    """How far the spine's track reaches, and whether that is a guess."""

    def calculate(
        self,
        total_chapters: int | None,
        observed_max: int | None,
        is_finished: bool = False,
    ) -> tuple[int, bool]:
        """Return `(max_chapter, is_estimated)`.

        `is_estimated` says the far end of the track is a guess — that the
        book is still being read and nobody has said where it ends. It is not a
        record of whether the number was adjusted: a stated total that a post
        overshoots is still not an estimate.

        Three sources, in order of how much they are worth:

        1. A stated total. The book told us, so believe it.
        2. A finished book's furthest posted chapter. Headroom exists to leave
           room for chapters not yet reached, and a finished book has none — so
           adding 20% draws the last tick at 83% of the track and tells someone
           who has read the whole book that there is more of it. The furthest
           chapter anyone reached is the best evidence of where it ends, and on
           a book that is over it is evidence rather than a guess.
        3. Neither: infer from the furthest chapter with headroom, and say so.

        The app now refuses to write a chapter past a book's stated total, and
        refuses to shorten a book below its posts, so an overshoot can only
        arrive from a row edited directly in Notion. Case 1 stays because that
        route is documented and supported — the spine's job is to contain the
        post it is given while staying honest about where its scale came from.
        """
        observed = observed_max or 0
        if total_chapters is not None:
            return max(total_chapters, observed), False
        if is_finished and observed:
            # Marked finished with nothing posted leaves nothing to infer from,
            # so that case falls through to the guess rather than returning a
            # scale of zero.
            return observed, False
        return max(math.ceil(observed * HEADROOM), MIN_SCALE), True
