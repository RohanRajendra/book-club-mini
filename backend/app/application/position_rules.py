"""Position rules that need the book, shared by the use cases that write posts.

`Book.contains_chapter` is the rule; this is the sentence a member reads when
they break it. It lives in one place because `CreatePost` and `EditPost` must
say the same thing — two copies of a user-facing string is how the wording of
one path drifts from the other.
"""

from __future__ import annotations

from app.domain import errors
from app.domain.entities import Book


def chapter_beyond_book(book: Book, chapter: int) -> errors.ChapterBeyondBook:
    return errors.ChapterBeyondBook(
        f"{book.title} has {book.total_chapters} chapters, so there is no "
        f"chapter {chapter}."
    )


def total_below_posts(total_chapters: int, highest: int, count: int) -> errors.TotalChaptersBelowPosts:
    posts = "post is" if count == 1 else "posts are"
    return errors.TotalChaptersBelowPosts(
        f"{count} {posts} past chapter {total_chapters} — the furthest is "
        f"chapter {highest}. Move or delete them first."
    )
