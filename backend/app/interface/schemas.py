"""Request and response DTOs, separate from domain entities.

The domain must not grow a `model_config`, and the API must not break when a
domain field is renamed. Conversion is explicit, in one direction, in one place.
"""

from __future__ import annotations

from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.application.dto import Feed, FeedPost
from app.domain.entities import Book, Post
from app.domain.values import BookStatus, Position, PostType


class PositionResponse(BaseModel):
    chapter: int
    page: int | None = None

    @classmethod
    def of(cls, position: Position | None) -> "PositionResponse | None":
        if position is None:
            return None
        return cls(chapter=position.chapter, page=position.page)


class BookResponse(BaseModel):
    id: str
    title: str
    author: str | None
    status: BookStatus
    total_chapters: int | None

    @classmethod
    def of(cls, book: Book) -> "BookResponse":
        return cls(
            id=book.id.value,
            title=book.title,
            author=book.author,
            status=book.status,
            total_chapters=book.total_chapters,
        )


class PostResponse(BaseModel):
    """Never carries the full body. `is_spoiler` and `is_own` are computed
    server-side, so the client never sees the blur rule or the ownership rule."""

    id: str
    member: str
    type: PostType
    body_preview: str
    has_full_body: bool
    position: PositionResponse | None
    parent_post_id: str | None
    created_at: datetime | None
    edited_at: datetime | None
    was_edited: bool
    is_spoiler: bool
    is_own: bool
    replies: list["PostResponse"] = Field(default_factory=list)

    @classmethod
    def of(cls, item: FeedPost) -> "PostResponse":
        post: Post = item.post
        return cls(
            id=post.id.value,
            member=post.member.value,
            type=post.type,
            body_preview=post.body_preview,
            has_full_body=post.has_full_body,
            position=PositionResponse.of(post.position),
            parent_post_id=(
                post.parent_post_id.value if post.parent_post_id else None
            ),
            created_at=post.created_at,
            edited_at=post.edited_at,
            was_edited=post.was_edited,
            is_spoiler=item.is_spoiler,
            is_own=item.is_own,
            replies=[cls.of(reply) for reply in item.replies],
        )


class MemberPositionResponse(BaseModel):
    member: str
    position: PositionResponse | None


class SpineResponse(BaseModel):
    max_chapter: int
    is_estimated: bool


class FeedResponse(BaseModel):
    book: BookResponse
    posts: list[PostResponse]
    #: One entry per roster member, in roster order — reader colours are
    #: assigned by index, and the spine renders "hasn't started" as a state.
    positions: list[MemberPositionResponse]
    spine: SpineResponse
    #: All four chip counts, so the client filters locally.
    counts: dict[str, int]

    @classmethod
    def of(cls, feed: Feed) -> "FeedResponse":
        return cls(
            book=BookResponse.of(feed.book),
            posts=[PostResponse.of(item) for item in feed.posts],
            positions=[
                MemberPositionResponse(
                    member=member.value, position=PositionResponse.of(position)
                )
                for member, position in feed.positions.items()
            ],
            spine=SpineResponse(
                max_chapter=feed.spine.max_chapter,
                is_estimated=feed.spine.is_estimated,
            ),
            counts=feed.counts,
        )


#: Sanity ceilings, not the business rule. Whether a chapter fits *this* book
#: needs the book and is decided in the use case; these only stop a value that
#: could never be a chapter from reaching Notion's number property, which
#: round-trips through a float and loses precision above 2**53.
MAX_CHAPTER = 10_000
MAX_PAGE = 100_000

#: An identifier arriving in a request body. Stripped, and empty after
#: stripping is a 422 — the value object raises on a blank id, and that
#: exception reaching the router used to surface as a 500.
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BookRequest(BaseModel):
    title: str
    author: str | None = None
    status: BookStatus = BookStatus.UPCOMING
    total_chapters: int | None = Field(default=None, ge=1, le=MAX_CHAPTER)


class CreatePostRequest(BaseModel):
    book_id: Identifier
    type: PostType
    body: str = ""
    chapter: int | None = Field(default=None, ge=1, le=MAX_CHAPTER)
    page: int | None = Field(default=None, ge=1, le=MAX_PAGE)
    parent_post_id: Identifier | None = None


class EditPostRequest(BaseModel):
    body: str = ""
    chapter: int | None = Field(default=None, ge=1, le=MAX_CHAPTER)
    page: int | None = Field(default=None, ge=1, le=MAX_PAGE)


class BodyResponse(BaseModel):
    body: str


class MeResponse(BaseModel):
    member: str
    members: list[str]
    reader_index: int


class HealthResponse(BaseModel):
    status: str
    books_data_source_id: str | None
    posts_data_source_id: str | None


class ErrorResponse(BaseModel):
    error: str
