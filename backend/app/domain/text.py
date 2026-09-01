"""How long a piece of text is, measured the way the store measures it.

Notion's 2000-character property limit counts **UTF-16 code units**, not Unicode
code points. Confirmed against the live API, which rejects 1001 astral emoji —
1001 code points — with:

    content.length should be ≤ `2000`, instead was `2002`

Python's `len` counts code points, so every limit in this app was measuring the
wrong quantity. An emoji-heavy 1900-character preview is 3800 units, and the
write fails with a 502 the member reads as "Can't reach Notion right now".

Nothing here is Notion-specific in shape: any store fronted by a runtime whose
strings are UTF-16 counts the same way.
"""

from __future__ import annotations

#: Above this code point a character needs a surrogate pair, so two units.
_ASTRAL = 0xFFFF


def utf16_length(text: str) -> int:
    """Length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def clip_to_utf16(text: str, limit: int) -> str:
    """The longest prefix of `text` fitting in `limit` UTF-16 code units.

    Cuts between code points, never inside one. Slicing by unit count directly
    would split a surrogate pair and leave an unpaired surrogate — text no
    store will accept and no reader can render — so an astral character that
    does not fit is dropped whole.
    """
    if utf16_length(text) <= limit:
        return text

    units = 0
    for index, char in enumerate(text):
        cost = 2 if ord(char) > _ASTRAL else 1
        if units + cost > limit:
            return text[:index]
        units += cost
    return text
