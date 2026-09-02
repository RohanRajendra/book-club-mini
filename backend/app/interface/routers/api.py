"""The API surface.

A router does three things: parse the DTO, call one use case, map the Result.
Anything else is misplaced.
"""

from __future__ import annotations

import asyncio

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from app.application.use_cases.books import BookCommand
from app.application.use_cases.create_post import CreatePostCommand
from app.application.use_cases.delete_post import DeletePostCommand
from app.application.use_cases.edit_post import EditPostCommand
from app.application.use_cases.get_feed import FeedQuery
from app.application.use_cases.get_post_body import PostBodyQuery
from app.composition import Container
from app.config import AuthMode
from app.interface import session
from app.interface.passphrase import verify_passphrase
from app.domain.values import BookId, MemberName, PostId, PostType
from app.interface.errors import raise_for
from app.interface.schemas import (
    FeedFilter,
    BodyResponse,
    BookRequest,
    BookResponse,
    CreatePostRequest,
    EditPostRequest,
    FeedResponse,
    HealthResponse,
    MeResponse,
    SessionRequest,
    PostResponse,
)

router = APIRouter(prefix="/api")


def container_of(request: Request) -> Container:
    return request.app.state.container


def _identifier(kind, raw: str):
    """Turn a path segment into a typed identifier, or reject the request.

    The value-object guard raises `ValueError`, which is correct for a
    programming error and wrong for user input: built straight from the path it
    escaped to the catch-all handler, so `/api/books/%20/feed` answered 500. The
    rule is not restated here — the exception is translated.
    """
    try:
        return kind(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="That isn't a valid id.") from None


def book_id_of(book_id: str = Path(...)) -> BookId:
    return _identifier(BookId, book_id)


def post_id_of(post_id: str = Path(...)) -> PostId:
    return _identifier(PostId, post_id)


BookIdPath = Annotated[BookId, Depends(book_id_of)]
PostIdPath = Annotated[PostId, Depends(post_id_of)]


def viewer_of(
    request: Request, container: Container = Depends(container_of)
) -> MemberName:
    """Who is asking.

    This used to be one configuration value, `container.member`, which was
    correct while the app was a process on one person's machine and wrong the
    moment two people share a deployment: both would be the same person, and
    every post either of them wrote would be attributed to whoever the server
    was configured as.

    Under `open` there is still no login, so the configured member stands. A
    cookie is honoured if one happens to be present, which is what lets the
    sign-in flow be exercised locally.

    The name is checked against the roster because a signature only proves the
    app issued the token — it says nothing about a roster edited since. A
    member removed from MEMBERS is signed out by that alone.
    """
    settings = container.settings
    if settings.session_secret:
        signed = session.read(
            request.cookies.get(session.COOKIE_NAME), settings.session_secret
        )
        if signed is not None:
            member = MemberName(signed)
            if member in container.roster:
                # Recorded so `/api/me` can tell the browser whether there is
                # a session to sign out of.
                request.state.from_session = True
                return container.canonical(member)

    if settings.auth_mode is AuthMode.OPEN and container.member is not None:
        return container.member

    raise HTTPException(status_code=401, detail="Sign in to continue.")


Viewer = Annotated[MemberName, Depends(viewer_of)]

#: For routes that need a signed-in member but not their name. Declaring it as
#: a dependency rather than an unused parameter keeps "you must be signed in"
#: visible in the decorator, where the route's other guarantees live.
RequiresSession = [Depends(viewer_of)]


def unwrap(result):
    if not result.is_ok():
        raise_for(result)
    return result.unwrap()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


#: A failed attempt costs this much wall time on top of the hash. Modest on
#: purpose: PBKDF2 already makes each attempt cost ~90ms of CPU, and no delay
#: this side of unusable defends a weak passphrase. What defends it is entropy,
#: which is why `scripts/make_secrets.py` generates one rather than asking for
#: it. A process-local attempt counter would be theatre on a platform that
#: starts a fresh process whenever it likes.
FAILED_SIGN_IN_DELAY = 0.5


def _sign_in_configured(settings) -> bool:
    """Whether this installation can verify a passphrase at all.

    Keyed on the secrets rather than on `auth_mode`, so the flow can be
    exercised locally by setting them without switching the whole installation
    over to requiring a login.
    """
    return bool(settings.session_secret and settings.site_passphrase_hash)


@router.post("/session", response_model=MeResponse)
async def sign_in(
    payload: SessionRequest,
    response: Response,
    container: Container = Depends(container_of),
) -> MeResponse:
    """Exchange the shared passphrase and a name for a session cookie."""
    settings = container.settings
    if not _sign_in_configured(settings):
        raise HTTPException(
            status_code=404, detail="This installation has no sign-in."
        )

    member = MemberName(payload.member)
    if member not in container.roster:
        # Refused for the same reason a wrong passphrase is, and with the same
        # sentence: which half was wrong is not the caller's business.
        await asyncio.sleep(FAILED_SIGN_IN_DELAY)
        raise HTTPException(status_code=401, detail="That didn't work.")

    if not verify_passphrase(payload.passphrase, settings.site_passphrase_hash):
        await asyncio.sleep(FAILED_SIGN_IN_DELAY)
        raise HTTPException(status_code=401, detail="That didn't work.")

    # The roster's spelling, not whatever was typed: it is what gets written
    # into Notion and rendered back, so it should not depend on the shift key.
    member = container.canonical(member)

    response.set_cookie(
        session.COOKIE_NAME,
        session.issue(member.value, settings.session_secret),
        max_age=session.MAX_AGE_SECONDS,
        httponly=True,
        # Lax rather than Strict: the cookie must survive following a link to
        # the app from anywhere, and the app is same-origin so nothing needs it
        # cross-site. It still keeps the cookie off a cross-site POST.
        samesite="lax",
        # An `open` installation is by definition local, and a Secure cookie is
        # dropped over plain HTTP — which would make the flow untestable there.
        secure=settings.auth_mode is AuthMode.PASSPHRASE,
        path="/",
    )
    return MeResponse(
        member=member.value,
        members=settings.members,
        reader_index=container.reader_index(member),
        signed_in=True,
    )


@router.delete("/session", status_code=204)
async def sign_out(response: Response) -> Response:
    """Always succeeds, signed in or not. Signing out twice is not an error,
    and reporting one would only tell a caller whether a cookie was valid."""
    response.delete_cookie(session.COOKIE_NAME, path="/")
    return Response(status_code=204, headers=dict(response.headers))


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    viewer: Viewer,
    container: Container = Depends(container_of),
) -> MeResponse:
    """Who this browser is, and the roster it belongs to.

    `reader_index` selects a colour and now comes from the viewer rather than
    from configuration, because under a shared deployment the two members read
    the same server.
    """
    return MeResponse(
        member=viewer.value,
        members=container.settings.members,
        reader_index=container.reader_index(viewer),
        signed_in=getattr(request.state, "from_session", False),
    )


@router.get(
    "/books", response_model=list[BookResponse], dependencies=RequiresSession
)
async def list_books(container: Container = Depends(container_of)):
    books = unwrap(await container.list_books().execute())
    return [BookResponse.of(book) for book in books]


@router.post(
    "/books",
    response_model=BookResponse,
    status_code=201,
    dependencies=RequiresSession,
)
async def add_book(
    payload: BookRequest, container: Container = Depends(container_of)
):
    book = unwrap(await container.add_book().execute(_book_command(payload)))
    return BookResponse.of(book)


@router.patch(
    "/books/{book_id}", response_model=BookResponse, dependencies=RequiresSession
)
async def update_book(
    book_id: BookIdPath,
    payload: BookRequest,
    container: Container = Depends(container_of),
):
    book = unwrap(
        await container.update_book().execute(book_id, _book_command(payload))
    )
    return BookResponse.of(book)


@router.get("/books/{book_id}/feed", response_model=FeedResponse)
async def get_feed(
    book_id: BookIdPath,
    viewer: Viewer,
    type: FeedFilter | None = Query(default=None),
    as_member: str | None = Query(default=None, alias="as"),
    container: Container = Depends(container_of),
):
    """`as` backs the View as control. It changes only which member's position
    drives the spoiler flags — it never changes post attribution."""
    if as_member is not None:
        # Compared as MemberName, which folds case: the roster is typed into a
        # config file and Notion's Member column is typed by hand, so `ada` and
        # `Ada` naming one person must not be a 400.
        requested = MemberName(as_member)
        if requested not in container.roster:
            raise HTTPException(
                status_code=400, detail=f"{as_member} is not in this club."
            )
        viewer = requested

    feed = unwrap(
        await container.get_feed().execute(
            FeedQuery(
                book_id=book_id,
                viewer=viewer,
                post_type=PostType(type.value) if type else None,
            )
        )
    )
    return FeedResponse.of(feed)


@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    payload: CreatePostRequest,
    viewer: Viewer,
    container: Container = Depends(container_of),
):
    post = unwrap(
        await container.create_post().execute(
            CreatePostCommand(
                book_id=BookId(payload.book_id),
                # Attribution is always whoever is signed in, never the request
                # body. The `as` control does not change it either.
                member=viewer,
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
    post_id: PostIdPath,
    payload: EditPostRequest,
    viewer: Viewer,
    container: Container = Depends(container_of),
):
    post = unwrap(
        await container.edit_post().execute(
            EditPostCommand(
                post_id=post_id,
                member=viewer,
                body=payload.body,
                chapter=payload.chapter,
                page=payload.page,
            )
        )
    )
    return _own_post(post)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: PostIdPath,
    viewer: Viewer,
    container: Container = Depends(container_of),
):
    unwrap(
        await container.delete_post().execute(
            DeletePostCommand(post_id=post_id, member=viewer)
        )
    )
    return Response(status_code=204)


@router.get("/posts/{post_id}/body", response_model=BodyResponse)
async def get_post_body(
    post_id: PostIdPath,
    viewer: Viewer,
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
                post_id=post_id, viewer=viewer, reveal=reveal
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
