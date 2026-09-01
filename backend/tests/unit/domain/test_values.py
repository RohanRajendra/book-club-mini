import pytest

from app.domain.values import BookId, MemberName, Position, PostId, PostType


def at(chapter: int, page: int | None = None) -> Position:
    return Position(chapter=chapter, page=page)


class TestPosition:
    def test_position_rejects_zero_or_negative_chapter(self):
        for chapter in (0, -1):
            with pytest.raises(ValueError, match="chapter"):
                at(chapter)

    def test_position_rejects_zero_or_negative_page(self):
        for page in (0, -3):
            with pytest.raises(ValueError, match="page"):
                at(5, page)

    def test_position_allows_missing_page(self):
        assert at(5).page is None

    def test_position_is_ahead_of_compares_chapter_first(self):
        assert at(9).is_ahead_of(at(4))
        assert not at(4).is_ahead_of(at(9))

    def test_position_is_ahead_of_compares_page_within_same_chapter(self):
        assert at(9, 204).is_ahead_of(at(9, 180))
        assert not at(9, 180).is_ahead_of(at(9, 204))

    def test_position_is_not_ahead_when_either_page_missing_in_same_chapter(self):
        """Genuinely incomparable — one member may be on audio with no pages."""
        assert not at(9).is_ahead_of(at(9, 180))
        assert not at(9, 204).is_ahead_of(at(9))
        assert not at(9).is_ahead_of(at(9))

    def test_position_equal_chapter_and_page_is_not_ahead(self):
        assert not at(9, 204).is_ahead_of(at(9, 204))

    def test_a_later_chapter_wins_even_with_an_earlier_page(self):
        """Chapter dominates: different editions do not share page numbers."""
        assert at(10, 2).is_ahead_of(at(9, 400))

    def test_position_has_no_ordering_operators(self):
        """A comparison operator would force a false answer for the
        incomparable case; a named method returning False is honest."""
        with pytest.raises(TypeError):
            at(9) < at(10)

    def test_position_is_frozen(self):
        with pytest.raises(Exception):
            at(9).chapter = 10


class TestIdentifiers:
    @pytest.mark.parametrize("wrapper", [MemberName, BookId, PostId])
    def test_identifiers_reject_an_empty_value(self, wrapper):
        with pytest.raises(ValueError):
            wrapper("")
        with pytest.raises(ValueError):
            wrapper("   ")

    @pytest.mark.parametrize("wrapper", [MemberName, BookId, PostId])
    def test_identifiers_render_as_their_value(self, wrapper):
        assert str(wrapper("abc")) == "abc"

    def test_distinct_identifier_types_are_not_equal(self):
        """This is the argument-order bug the wrappers exist to catch, and it
        is caught at runtime because the project has no type checker."""
        assert BookId("x") != PostId("x")

    def test_identifiers_of_the_same_type_compare_by_value(self):
        assert BookId("x") == BookId("x")
        assert BookId("x") != BookId("y")

    def test_identifiers_are_hashable(self):
        assert len({BookId("x"), BookId("x"), BookId("y")}) == 2


class TestPostType:
    def test_the_four_post_types_exist(self):
        assert {t.value for t in PostType} == {
            "Progress",
            "Thought",
            "Question",
            "Reply",
        }

    def test_post_type_values_match_the_notion_select_options(self):
        """The values are written into Notion's Type select verbatim."""
        assert PostType.PROGRESS.value == "Progress"
        assert PostType.REPLY.value == "Reply"


class TestMemberNameIsCaseInsensitive:
    """Notion's Member column is a free-text select, typed by hand.

    A roster of `Ada` against a Notion value of `ada` made two people. The
    concrete harm: your own posts are blurred back at you, because the spoiler
    rule asks whether the author is the viewer and a string comparison said no.
    """

    def test_names_differing_only_by_case_are_the_same_member(self):
        assert MemberName("Ada") == MemberName("ada")

    def test_they_hash_alike_so_they_are_one_key_in_a_position_map(self):
        """PositionResolver keys a dict by member. Two spellings meant two
        entries, and the roster lookup found neither."""
        assert len({MemberName("Ada"), MemberName("ADA")}) == 1
        assert {MemberName("Ada"): 1}[MemberName("aDa")] == 1

    def test_a_roster_membership_test_ignores_case(self):
        assert MemberName("ada") in [MemberName("Ada"), MemberName("Grace")]

    def test_different_names_are_still_different(self):
        assert MemberName("Ada") != MemberName("Grace")

    def test_surrounding_whitespace_still_distinguishes_nothing_else(self):
        """Case is the only thing folded. A name is not otherwise normalised,
        so this documents where the leniency stops."""
        assert MemberName("Ada ") != MemberName("Ada")

    def test_the_original_spelling_is_kept_for_display(self):
        assert MemberName("aDa").value == "aDa"
        assert str(MemberName("aDa")) == "aDa"

    def test_a_member_name_is_still_not_a_post_id(self):
        assert MemberName("Ada") != PostId("Ada")
