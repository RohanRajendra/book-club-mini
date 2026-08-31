from app.domain.errors import DomainError, all_domain_errors


def test_every_domain_error_has_a_unique_code():
    """Codes are what the HTTP layer maps on; a duplicate would silently
    collapse two failures into one response."""
    codes = [error.code for error in all_domain_errors()]
    assert len(codes) == len(set(codes)), sorted(codes)


def test_every_domain_error_declares_a_code():
    missing = [error.__name__ for error in all_domain_errors() if not error.code]
    assert not missing


def test_the_expected_failures_are_all_present():
    """The complete expected-failure taxonomy."""
    expected = {
        "BookNotFound",
        "PostNotFound",
        "NotPostOwner",
        "SpoilerWithheld",
        "CannotReplyToReply",
        "ReplyBookMismatch",
        "ChapterRequiredForProgress",
        "PageRequiresChapter",
        "ChapterBeyondBook",
        "TotalChaptersBelowPosts",
        "BodyRequired",
        "BodyTooLong",
        "TitleRequired",
        "UnknownMember",
    }
    assert {error.__name__ for error in all_domain_errors()} == expected


def test_a_domain_error_carries_a_human_message():
    from app.domain.errors import BookNotFound

    error = BookNotFound("That book isn't here any more.")
    assert error.message == "That book isn't here any more."
    assert isinstance(error, DomainError)


def test_domain_errors_are_not_exceptions():
    """Result carries them as values; they are expected outcomes, not faults."""
    assert not issubclass(DomainError, BaseException)
