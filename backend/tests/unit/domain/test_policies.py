"""The spoiler rule. This test list is the specification: each name states a
rule, and together they define when a post is blurred."""

from app.domain.entities import Post
from app.domain.policies import ChapterFirstSpoilerPolicy, SpoilerPolicy
from app.domain.values import BookId, MemberName, Position, PostId, PostType

ADA = MemberName("Ada")
GRACE = MemberName("Grace")

policy: SpoilerPolicy = ChapterFirstSpoilerPolicy()


def post_at(chapter: int | None, page: int | None = None, member=GRACE, **kw) -> Post:
    return Post(
        book_id=BookId("b1"),
        member=member,
        type=kw.pop("type", PostType.THOUGHT),
        body_preview="...",
        position=Position(chapter, page) if chapter is not None else None,
        **kw,
    )


def test_own_post_is_never_a_spoiler():
    assert not policy.is_spoiler(post_at(9, member=ADA), ADA, Position(4))


def test_own_post_far_ahead_is_still_not_a_spoiler():
    assert not policy.is_spoiler(post_at(400, member=ADA), ADA, Position(1))


def test_nothing_is_a_spoiler_when_viewer_position_unknown():
    """Blurring the whole feed for someone who has not posted progress makes
    the app look broken. The empty spine prompts them instead."""
    assert not policy.is_spoiler(post_at(400), ADA, None)


def test_post_without_chapter_is_never_a_spoiler():
    assert not policy.is_spoiler(post_at(None), ADA, Position(4))


def test_later_chapter_is_a_spoiler():
    assert policy.is_spoiler(post_at(9), ADA, Position(4))


def test_earlier_chapter_is_not_a_spoiler():
    assert not policy.is_spoiler(post_at(2), ADA, Position(4))


def test_same_chapter_later_page_is_a_spoiler():
    assert policy.is_spoiler(post_at(9, 204), ADA, Position(9, 180))


def test_same_chapter_earlier_page_is_not_a_spoiler():
    assert not policy.is_spoiler(post_at(9, 180), ADA, Position(9, 204))


def test_same_chapter_is_not_a_spoiler_when_post_page_missing():
    assert not policy.is_spoiler(post_at(9), ADA, Position(9, 180))


def test_same_chapter_is_not_a_spoiler_when_viewer_page_missing():
    assert not policy.is_spoiler(post_at(9, 204), ADA, Position(9))


def test_same_chapter_same_page_is_not_a_spoiler():
    assert not policy.is_spoiler(post_at(9, 204), ADA, Position(9, 204))


def test_reply_is_evaluated_on_its_own_copied_position():
    """A reply copies its parent's position at creation, so it is judged on
    that copy with no lookup of the parent."""
    reply = post_at(9, 204, type=PostType.REPLY, parent_post_id=PostId("parent"))
    assert policy.is_spoiler(reply, ADA, Position(4))
    assert not policy.is_spoiler(reply, ADA, Position(12))


def test_the_policy_delegates_ordering_to_position(monkeypatch):
    """Two copies of the ordering rule is how they drift."""
    calls = []
    original = Position.is_ahead_of

    def spy(self, other):
        calls.append((self, other))
        return original(self, other)

    monkeypatch.setattr(Position, "is_ahead_of", spy)
    policy.is_spoiler(post_at(9), ADA, Position(4))
    assert calls == [(Position(9), Position(4))]
