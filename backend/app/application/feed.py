"""Assembling the feed: nesting, ordering, positions, spoiler flags, scale."""

from __future__ import annotations

from app.application.dto import Feed, FeedPost, Spine
from app.domain.entities import Book, Post
from app.domain.policies import SpoilerPolicy
from app.domain.services import PositionResolver, ScaleCalculator
from app.domain.values import MemberName, PostType

#: The filter chip labels exposed to the client.
COUNT_KEYS = {
    PostType.PROGRESS: "progress",
    PostType.THOUGHT: "thought",
    PostType.QUESTION: "question",
}


class FeedAssembler:
    def __init__(
        self,
        spoiler_policy: SpoilerPolicy,
        position_resolver: PositionResolver,
        scale_calculator: ScaleCalculator,
        roster: list[MemberName],
    ) -> None:
        self._spoilers = spoiler_policy
        self._positions = position_resolver
        self._scale = scale_calculator
        self._roster = roster

    def assemble(
        self,
        book: Book,
        posts: list[Post],
        viewer: MemberName,
        post_type: PostType | None = None,
    ) -> Feed:
        positions = self._positions.resolve(posts)
        viewer_position = positions.get(viewer)

        top_level = [post for post in posts if not post.is_reply]
        top_level.sort(key=lambda post: post.created_at, reverse=True)

        replies_by_parent: dict[str, list[Post]] = {}
        for post in posts:
            if post.is_reply:
                replies_by_parent.setdefault(post.parent_post_id.value, []).append(post)
        for group in replies_by_parent.values():
            # A conversation reads downward inside a feed that reads upward.
            group.sort(key=lambda post: post.created_at)

        counts = {"all": len(top_level)} | {
            key: sum(1 for post in top_level if post.type is post_type_)
            for post_type_, key in COUNT_KEYS.items()
        }

        # The filter runs after nesting, never in the query: filtering to
        # Thought in Notion would strip the replies off the thoughts. Orphan
        # replies — whose parent is missing or filtered away — are dropped.
        if post_type is not None:
            top_level = [post for post in top_level if post.type is post_type]

        assembled = [
            FeedPost(
                post=post,
                is_spoiler=self._spoilers.is_spoiler(post, viewer, viewer_position),
                is_own=post.member == viewer,
                replies=[
                    FeedPost(
                        post=reply,
                        # Flagged independently rather than inheriting the
                        # parent's flag: revealing a parent must not silently
                        # reveal replies the member has not chosen to see.
                        is_spoiler=self._spoilers.is_spoiler(
                            reply, viewer, viewer_position
                        ),
                        is_own=reply.member == viewer,
                    )
                    for reply in replies_by_parent.get(post.id.value, [])
                ],
            )
            for post in top_level
        ]

        observed = [post.position.chapter for post in posts if post.position]
        max_chapter, is_estimated = self._scale.calculate(
            book.total_chapters, max(observed) if observed else None
        )

        return Feed(
            book=book,
            posts=assembled,
            # Every roster member appears, with None for anyone who has not
            # posted progress. The spine renders "hasn't started" as a state
            # and cannot if the member is simply absent from the mapping.
            positions={member: positions.get(member) for member in self._roster},
            spine=Spine(max_chapter=max_chapter, is_estimated=is_estimated),
            counts=counts,
        )
