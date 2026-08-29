"""Domain error → HTTP status, in one table.

Adding a domain error without adding a mapping fails an architecture test,
because the default would otherwise be a silent 500 in production.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.domain import errors
from app.domain.result import Err

#: Keyed on DomainError.code.
STATUS_BY_CODE: dict[str, int] = {
    errors.BookNotFound.code: 404,
    errors.PostNotFound.code: 404,
    errors.NotPostOwner.code: 403,
    errors.CannotReplyToReply.code: 400,
    errors.ReplyBookMismatch.code: 400,
    errors.ChapterRequiredForProgress.code: 400,
    errors.PageRequiresChapter.code: 400,
    errors.BodyRequired.code: 400,
    errors.BodyTooLong.code: 400,
    errors.TitleRequired.code: 400,
    errors.UnknownMember.code: 400,
}

#: Matches the UX copy exactly, so the frontend can display it verbatim rather
#: than substituting its own (01-ux-spec.md §Empty and error copy).
NOTION_UNREACHABLE = "Can't reach Notion right now. Try refreshing."

UNEXPECTED = "Something went wrong. Try refreshing."


def raise_for(err: Err) -> None:
    """Translate an `Err` into the HTTP response it maps to."""
    error = err.unwrap_err()
    status = STATUS_BY_CODE.get(error.code, 500)
    raise HTTPException(status_code=status, detail=error.message)


def error_response(status: int, message: str) -> JSONResponse:
    """Every error body is `{"error": "<one human sentence>"}`."""
    return JSONResponse(status_code=status, content={"error": message})
