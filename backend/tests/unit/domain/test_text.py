"""Measuring text the way the store measures it."""

from __future__ import annotations

import pytest

from app.domain.text import clip_to_utf16, utf16_length

#: One code point, two UTF-16 code units. The whole point of this module.
EMOJI = "\U0001F600"

#: One code point, one UTF-16 code unit, three UTF-8 bytes — so a test that
#: passes for this and for EMOJI is not accidentally measuring bytes.
BMP = "é"


class TestUtf16Length:
    def test_ascii_counts_one_per_character(self):
        assert utf16_length("hello") == 5

    def test_a_non_ascii_character_inside_the_bmp_still_counts_one(self):
        assert utf16_length(BMP * 5) == 5

    def test_an_astral_character_counts_two(self):
        assert utf16_length(EMOJI) == 2

    def test_a_mixture_adds_up(self):
        assert utf16_length(f"a{EMOJI}b{BMP}") == 5

    def test_empty_is_zero(self):
        assert utf16_length("") == 0

    def test_it_is_not_measuring_utf8_bytes(self):
        """é is one UTF-16 unit and two UTF-8 bytes. Getting this wrong would
        make every accented title fail a limit it fits inside."""
        assert utf16_length(BMP) == 1


class TestClipToUtf16:
    def test_text_within_the_limit_is_returned_whole(self):
        assert clip_to_utf16("hello", 10) == "hello"

    def test_text_at_exactly_the_limit_is_returned_whole(self):
        assert clip_to_utf16("hello", 5) == "hello"

    def test_ascii_is_cut_at_the_limit(self):
        assert clip_to_utf16("abcdef", 3) == "abc"

    def test_astral_characters_are_counted_as_two(self):
        assert clip_to_utf16(EMOJI * 5, 4) == EMOJI * 2

    def test_an_astral_character_is_dropped_whole_rather_than_halved(self):
        """Cutting between the two units of a surrogate pair would produce an
        unpaired surrogate — text no store will accept and no reader can
        render."""
        clipped = clip_to_utf16(EMOJI * 5, 5)
        assert clipped == EMOJI * 2
        assert utf16_length(clipped) == 4
        clipped.encode("utf-8")  # would raise on a lone surrogate

    def test_a_limit_of_zero_returns_nothing(self):
        assert clip_to_utf16("abc", 0) == ""

    @pytest.mark.parametrize("limit", range(0, 12))
    def test_the_result_never_exceeds_the_limit(self, limit):
        for text in ("abcdef", EMOJI * 5, f"a{EMOJI}{BMP}{EMOJI}b"):
            assert utf16_length(clip_to_utf16(text, limit)) <= limit
