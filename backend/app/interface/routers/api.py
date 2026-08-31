"""The API surface.

A router does three things: parse the DTO, call one use case, map the Result.
Anything else is misplaced.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.application.use_cases.books import BookCommand
from app.application.use_cases.create_post import CreatePostCommand
from app.application.use_cases.delete_post import DeletePostCommand
from app.application.use_cases.edit_post import EditPostCommand
from app.application.use_cases.get_feed import FeedQuery
from app.application.use_cases.get_post_body import PostBodyQuery
from app.composition import Container
from app.domain.values import BookId, MemberName, PostId, PostType
from app.interface.errors import raise_for
from app.interface.schemas import (
    BodyResponse,
    BookRequest,
    BookResponse,
    CreatePostRequest,
    EditPostRequest,
    FeedResponse,
    HealthResponse,
    MeResponse,
    PostResponse,
)

router = APIRouter(prefix="/api")


def container_of(request: Request) -> Container:
    return request.app.state.container


def unwrap(result):
    if not result.is_ok():
        raise_for(result)
    return result.unwrap()


@router.get("/health", response_model=HealthResponse)
async def health(container: Container = Depends(container_of)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        books_data_source_id=container.books_data_source_id,
        posts_data_source_id=container.posts_data_source_id,
    )


@router.get("/me", response_model=MeResponse)
async def me(container: Container = Depends(container_of)) -> MeResponse:
    """Identity comes from MEMBER_NAME in this installation's .env. There is no
    session and no auth route."""
    return MeResponse(
        member=container.settings.member_name,
        members=container.settings.members,
        reader_index=container.settings.reader_index,
    )


@router.get("/books", response_model=list[BookResponse])
async def list_books(container: Container = Depends(container_of)):
    books = unwrap(await container.list_books().execute())
    return [BookResponse.of(book) for book in books]


@router.post("/books", response_model=BookResponse, status_code=201)
async def add_book(
    payload: BookRequest, container: Container = Depends(container_of)
):
    book = unwrap(await container.add_book().execute(_book_command(payload)))
    return BookResponse.of(book)


@router.patch("/books/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: str,
    payload: BookRequest,
    container: Container = Depends(container_of),
):
    book = unwrap(
        await container.update_book().execute(BookId(book_id), _book_command(payload))
    )
    return BookResponse.of(book)


@router.get("/books/{book_id}/feed", response_model=FeedResponse)
async def get_feed(
    book_id: str,
    type: PostType | None = Query(default=None),
    as_member: str | None = Query(default=None, alias="as"),
    container: Container = Depends(container_of),
):
    """`as` backs the View as control. It changes only which member's position
    drives the spoiler flags — it never changes post attribution."""
    viewer = container.member
    if as_member is not None:
        if as_member not in container.settings.members:
            raise HTTPException(
                status_code=400, detail=f"{as_member} is not in this club."
            )
        viewer = MemberName(as_member)

    feed = unwrap(
        await container.get_feed().execute(
            FeedQuery(book_id=BookId(book_id), viewer=viewer, post_type=type)
        )
    )
    return FeedResponse.of(feed)


@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    payload: CreatePostRequest, container: Container = Depends(container_of)
):
    post = unwrap(
        await container.create_post().execute(
            CreatePostCommand(
                book_id=BookId(payload.book_id),
                # Attribution is always this installation's member, never the
                # request body. The `as` control does not change it either.
                member=container.member,
                type=payload.type,
                body=payload.body,
                chapter=payload.chapter,
                page=payload.page,
                parent_post_id=(
                    PostId(payload.parent_post_id) if payload.parent_post_id else None
                ),
            )
        )
    )
    return _own_post(post)


@router.patch("/posts/{post_id}", response_model=PostResponse)
async def edit_post(
    post_id: str,
    payload: EditPostRequest,
    container: Container = Depends(container_of),
):
    post = unwrap(
        await container.edit_post().execute(
            EditPostCommand(
                post_id=PostId(post_id),
                member=container.member,
                body=payload.body,
                chapter=payload.chapter,
                page=payload.page,
            )
        )
    )
    return _own_post(post)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(post_id: str, container: Container = Depends(container_of)):
    unwrap(
        await container.delete_post().execute(
            DeletePostCommand(post_id=PostId(post_id), member=container.member)
        )
    )
    return Response(status_code=204)


@router.get("/posts/{post_id}/body", response_model=BodyResponse)
async def get_post_body(
    post_id: str,
    reveal: bool = Query(default=False),
    container: Container = Depends(container_of),
):
    """`reveal` carries the member's decision to read past their own position.

    Without it a post ahead of them is withheld: the feed already flags it as a
    spoiler, and blurring it in the browser while serving the text on request
    would leave the rule to the client."""
    body = unwrap(
        await container.get_post_body().execute(
            PostBodyQuery(
                post_id=PostId(post_id), viewer=container.member, reveal=reveal
            )
        )
    )
    return BodyResponse(body=body)


def _book_command(payload: BookRequest) -> BookCommand:
    return BookCommand(
        title=payload.title,
        author=payload.author,
        status=payload.status,
        total_chapters=payload.total_chapters,
    )


def _own_post(post) -> PostResponse:
    """A post you just wrote or edited is yours and is never a spoiler to you."""
    from app.application.dto import FeedPost

    return PostResponse.of(FeedPost(post=post, is_spoiler=False, is_own=True))
