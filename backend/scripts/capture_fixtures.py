#!/usr/bin/env python3
"""Record real Notion responses into tests/fixtures/notion/.

The mapper tests depend on real payload shapes, and hand-written approximations
are how a suite goes green against an API that would reject it.

    python scripts/capture_fixtures.py
    python scripts/capture_fixtures.py --seed-posts   # create two posts first

Workspace and user IDs are scrubbed. Page and block IDs are kept: the mapper
reads them, and they are meaningless outside the owner's workspace.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_notion import (  # noqa: E402
    NOTION_VERSION,
    TICK,
    client,
    get,
    load_env,
    require,
    resolve_data_source,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "notion"

# Only identity-bearing keys. Deliberately NOT "name": a select option value is
# {"id": ..., "name": "Thought", "color": ...}, and blanking that turns every
# Type, Status and Member into "scrubbed" — the fixture then asserts nothing and
# the mapper silently falls back, which is precisely the "green against an API
# that would reject it" failure these fixtures exist to prevent.
SCRUB_KEYS = {"avatar_url", "person", "email"}
SCRUB_OBJECTS = {"user", "bot"}

PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"


def scrub(value):
    """Drop user identity, keep every structural and select value."""
    if isinstance(value, dict):
        if value.get("object") in SCRUB_OBJECTS:
            return {"object": value["object"], "id": PLACEHOLDER_ID}
        return {
            key: ("scrubbed" if key in SCRUB_KEYS else scrub(inner))
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def rich_text_chunks(content: str) -> list[dict]:
    """A single rich text object caps at 2000 characters.

    The app's own to_rich_text does this; the seed path has to as well, or the
    append comes back 400 and the post is left claiming a body it does not have.
    """
    return [
        {"type": "text", "text": {"content": content[index : index + 2000]}}
        for index in range(0, len(content), 2000)
    ]


def write(name: str, payload: dict) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / name
    path.write_text(json.dumps(scrub(payload), indent=2) + "\n", encoding="utf-8")
    print(f"{TICK} {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


def seed_posts(http: httpx.Client, posts_ds: str, book_id: str) -> None:
    """One short top-level post and one long reply — the two shapes the mapper
    tests want to see."""
    short = http.post(
        "/pages",
        json={
            "parent": {"type": "data_source_id", "data_source_id": posts_ds},
            "properties": {
                "Name": {"title": [{"text": {"content": "Fixture · Ch 3 · Thought"}}]},
                "Book": {"relation": [{"id": book_id}]},
                "Member": {"select": {"name": "Fixture Member"}},
                "Type": {"select": {"name": "Thought"}},
                "Body Preview": {"rich_text": [{"text": {"content": "A short thought."}}]},
                "Has Full Body": {"checkbox": False},
                "Chapter": {"number": 3},
            },
        },
    ).json()

    body = "The house is the world and the world is the house. " * 60
    long_post = http.post(
        "/pages",
        json={
            "parent": {"type": "data_source_id", "data_source_id": posts_ds},
            "properties": {
                "Name": {"title": [{"text": {"content": "Fixture · Ch 3 · Reply"}}]},
                "Book": {"relation": [{"id": book_id}]},
                "Member": {"select": {"name": "Fixture Member"}},
                "Type": {"select": {"name": "Reply"}},
                "Body Preview": {"rich_text": [{"text": {"content": body[:1900]}}]},
                "Has Full Body": {"checkbox": True},
                "Chapter": {"number": 3},
                "Parent Post ID": {"rich_text": [{"text": {"content": short["id"]}}]},
            },
        },
    ).json()

    append = http.patch(
        f"/blocks/{long_post['id']}/children",
        json={
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": rich_text_chunks(body)},
                }
            ]
        },
    )
    if append.status_code >= 400:
        # Never swallow this: the post already claims Has Full Body, so a
        # silent failure leaves a "Read more" with nothing behind it.
        print(f"Block append failed: {append.status_code} {append.text[:300]}")
        raise SystemExit(1)

    print(f"{TICK} Seeded two fixture posts")
    return long_post["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-posts", action="store_true", help="create two posts first")
    args = parser.parse_args()

    token, books_db, posts_db = require(load_env())

    with client(token) as http:
        books_ds = resolve_data_source(http, "Books", books_db)
        posts_ds = resolve_data_source(http, "Posts", posts_db)

        write("database.json", get(http, f"/databases/{books_db}"))
        write("data_source.json", get(http, f"/data_sources/{books_ds}"))

        books = http.post(
            f"/data_sources/{books_ds}/query", json={"page_size": 5}
        ).json()
        if not books.get("results"):
            print("No books found. Run: python scripts/verify_notion.py --seed")
            return 1
        book_id = books["results"][0]["id"]
        write("page_create.json", books["results"][0])

        block_page = None
        if args.seed_posts:
            block_page = seed_posts(http, posts_ds, book_id)

        query = http.post(
            f"/data_sources/{posts_ds}/query",
            json={
                "page_size": 100,
                "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            },
        ).json()
        write("query.json", query)

        if len(query.get("results", [])) < 2:
            print(
                "  ! query.json has fewer than 2 rows. Post two things in the app, "
                "or rerun with --seed-posts."
            )

        if block_page is None:
            with_body = [
                row
                for row in query.get("results", [])
                if row["properties"].get("Has Full Body", {}).get("checkbox")
            ]
            block_page = with_body[0]["id"] if with_body else None

        if block_page:
            write(
                "block_children.json",
                get(http, f"/blocks/{block_page}/children?page_size=100"),
            )
        else:
            print(
                "  ! No post with Has Full Body. Post something over 1900 characters, "
                "or rerun with --seed-posts, then run this again."
            )
            return 1

    print(f"\n{TICK} Fixtures captured. Run: pytest tests/integration/test_mappers.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.RequestError as exc:
        print(f"Could not reach Notion: {exc}")
        sys.exit(1)
