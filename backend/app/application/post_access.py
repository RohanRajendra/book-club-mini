"""One definition of what makes a post unreachable.

`PostRepository.get` returns archived posts on purpose: a soft delete has to
stay recoverable, and every backend's porting checklist says so. The cost is
that deleted-ness becomes something each caller has to notice, and four use
cases read a post by id — edit, delete, fetch a body, and reply to a parent.
Asking here rather than at each call site is what stops those four drifting
apart, which is exactly how one of them ends up operating on a deleted post.

Absent and deleted give the same answer deliberately. A member who deleted a
post does not need to be told the difference, and telling them would leak that
the row is still there.
"""

from __future__ import annotations

from app.domain import errors
from app.domain.entities import Post


def post_is_gone(post: Post | None) -> errors.PostNotFound | None:
    """The error to return, or `None` when the post can be acted on."""
    if post is None or post.is_deleted:
        return errors.PostNotFound("That post is gone.")
    return None
