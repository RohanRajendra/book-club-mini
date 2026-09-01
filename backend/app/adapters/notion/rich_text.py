"""Rich text chunking, and readers for Notion's property shapes."""

from __future__ import annotations

from typing import Any

from app.domain.text import clip_to_utf16, utf16_length

#: A single rich text object caps at 2000 UTF-16 code units. Not code points:
#: Notion answers "content.length should be <= 2000, instead was 2002" to 1001
#: astral emoji. See domain/text.py.
CHUNK_SIZE = 2000

#: A rich text array holds at most 100 objects.
MAX_CHUNKS = 100

#: What 100 objects can be *relied* on to hold. Not 100 x 2000: an object
#: closes one unit short whenever the next character is astral and only one
#: unit of its budget is left, and a body can be built where that happens at
#: every boundary. At 100 x 2000 such a body is inside the ceiling and still
#: needs 101 objects, which Notion rejects.
MAX_CONTENT = MAX_CHUNKS * (CHUNK_SIZE - 1)


def to_rich_text(content: str) -> list[dict[str, Any]]:
    length = utf16_length(content)
    if length > MAX_CONTENT:
        raise ValueError(
            f"content must be at most {MAX_CONTENT} characters, got {length}"
        )
    if not content:
        return []

    # Sliced by unit budget rather than by character count, and cut only
    # between code points. A fixed character stride puts 4000 units in an
    # object when the text is astral, and slicing by unit index directly would
    # leave half a surrogate pair.
    chunks: list[dict[str, Any]] = []
    rest = content
    while rest:
        head = clip_to_utf16(rest, CHUNK_SIZE)
        chunks.append({"type": "text", "text": {"content": head}})
        rest = rest[len(head) :]
    return chunks


def from_rich_text(array: list[dict[str, Any]] | None) -> str:
    if not array:
        return ""
    return "".join(
        part.get("plain_text") or part.get("text", {}).get("content", "")
        for part in array
    )


def plain(properties: dict[str, Any], name: str) -> str:
    prop = properties.get(name) or {}
    return from_rich_text(prop.get("rich_text") or prop.get("title"))


def number(properties: dict[str, Any], name: str) -> int | None:
    prop = properties.get(name) or {}
    value = prop.get("number")
    return int(value) if value is not None else None


def checkbox(properties: dict[str, Any], name: str) -> bool:
    prop = properties.get(name) or {}
    return bool(prop.get("checkbox"))


def select_name(properties: dict[str, Any], name: str) -> str | None:
    prop = properties.get(name) or {}
    selected = prop.get("select")
    return selected.get("name") if selected else None


def relation_ids(properties: dict[str, Any], name: str) -> list[str]:
    prop = properties.get(name) or {}
    return [item["id"] for item in prop.get("relation") or []]
