"""Rich text chunking, and readers for Notion's property shapes."""

from __future__ import annotations

from typing import Any

#: A single rich text object caps at 2000 characters.
CHUNK_SIZE = 2000

#: A rich text array holds at most 100 objects, so ~200,000 characters.
MAX_CHUNKS = 100
MAX_CONTENT = CHUNK_SIZE * MAX_CHUNKS


def to_rich_text(content: str) -> list[dict[str, Any]]:
    if len(content) > MAX_CONTENT:
        raise ValueError(
            f"content must be at most {MAX_CONTENT} characters, got {len(content)}"
        )
    if not content:
        return []
    return [
        {"type": "text", "text": {"content": content[index : index + CHUNK_SIZE]}}
        for index in range(0, len(content), CHUNK_SIZE)
    ]


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
