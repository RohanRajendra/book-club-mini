#!/usr/bin/env python3
"""Check that the Notion workspace matches the schema this app expects.

Standalone operator tool: httpx only, no app imports, not under test. Run it
after creating the databases and after any hand-edit in Notion.

    python scripts/verify_notion.py
    python scripts/verify_notion.py --seed

Exits non-zero on any mismatch, so it can gate setup.sh.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

NOTION_VERSION = "2025-09-03"
BASE_URL = "https://api.notion.com/v1"

# 00-overview.md §Notion schema. Property name -> Notion property type.
BOOKS_SCHEMA = {
    "Title": "title",
    "Author": "rich_text",
    "Status": "select",
    "Total Chapters": "number",
}

POSTS_SCHEMA = {
    "Name": "title",
    "Book": "relation",
    "Member": "select",
    "Type": "select",
    "Body Preview": "rich_text",
    "Has Full Body": "checkbox",
    "Chapter": "number",
    "Page": "number",
    "Parent Post ID": "rich_text",
}

NOT_CONNECTED = (
    "Notion returned 404. The integration is probably not connected to the Book "
    "Club page — open the page, ••• → Connections, and add it."
)

TICK, CROSS = "✓", "✗"


REQUIRED = ("NOTION_TOKEN", "NOTION_BOOKS_DB_ID", "NOTION_POSTS_DB_ID")


def load_env() -> dict[str, str]:
    """backend/.env, with a real environment variable taking precedence."""
    values: dict[str, str] = {}
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    for key in REQUIRED:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def require(env: dict[str, str]) -> tuple[str, str, str]:
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        print(f"{CROSS} Missing required settings: {', '.join(missing)}")
        print("  Copy backend/.env.example to backend/.env and fill them in.")
        raise SystemExit(2)
    return env["NOTION_TOKEN"], env["NOTION_BOOKS_DB_ID"], env["NOTION_POSTS_DB_ID"]


def client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )


def get(http: httpx.Client, path: str) -> dict:
    response = http.get(path)
    if response.status_code == 404:
        print(f"{CROSS} 404 on {path}")
        print(f"  {NOT_CONNECTED}")
        raise SystemExit(1)
    if response.status_code == 401:
        print(f"{CROSS} 401 Unauthorized. NOTION_TOKEN is wrong or has been revoked.")
        raise SystemExit(1)
    if response.status_code >= 400:
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        print(f"{CROSS} {response.status_code} on {path}: {body.get('message', response.text[:200])}")
        raise SystemExit(1)
    return response.json()


def plain_title(obj: dict) -> str:
    return "".join(part.get("plain_text", "") for part in obj.get("title", [])) or "(untitled)"


def resolve_data_source(http: httpx.Client, label: str, database_id: str) -> str:
    """The ID in a Notion URL is the *database* ID. Rows live on its data source."""
    database = get(http, f"/databases/{database_id}")
    sources = database.get("data_sources") or []
    if not sources:
        print(f"{CROSS} {label}: database has no data sources. Recreate it in the Notion UI.")
        raise SystemExit(1)
    if len(sources) > 1:
        print(f"  ! {label}: {len(sources)} data sources found; this app uses the first only.")
    print(f"{TICK} {label}: {plain_title(database)!r}")
    print(f"    database_id    {database_id}")
    print(f"    data_source_id {sources[0]['id']}")
    return sources[0]["id"]


def check_schema(http: httpx.Client, label: str, data_source_id: str, expected: dict[str, str]) -> bool:
    actual = get(http, f"/data_sources/{data_source_id}").get("properties", {})
    print(f"\n  {label} properties")
    ok = True
    width = max(len(name) for name in expected)
    for name, want in expected.items():
        got = actual.get(name, {}).get("type")
        if got == want:
            print(f"    {TICK} {name.ljust(width)}  {want}")
        elif got is None:
            print(f"    {CROSS} {name.ljust(width)}  missing (expected {want})")
            ok = False
        else:
            print(f"    {CROSS} {name.ljust(width)}  is {got}, expected {want}")
            ok = False

    unexpected = sorted(set(actual) - set(expected))
    if unexpected:
        print(f"    ! extra properties (ignored): {', '.join(unexpected)}")
    return ok


def seed(http: httpx.Client, books_data_source_id: str) -> None:
    response = http.post(
        "/pages",
        json={
            # The parent is the DATA SOURCE id, not the database id.
            "parent": {"type": "data_source_id", "data_source_id": books_data_source_id},
            "properties": {
                "Title": {"title": [{"text": {"content": "Test Book"}}]},
                "Status": {"select": {"name": "Currently Reading"}},
            },
        },
    )
    if response.status_code >= 400:
        print(f"{CROSS} Seed failed: {response.status_code} {response.text[:300]}")
        raise SystemExit(1)
    print(f"\n{TICK} Seeded 'Test Book' as Currently Reading — {response.json().get('url', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="create one 'Currently Reading' book")
    args = parser.parse_args()

    token, books_db, posts_db = require(load_env())

    with client(token) as http:
        print("Resolving databases\n")
        books_ds = resolve_data_source(http, "Books", books_db)
        posts_ds = resolve_data_source(http, "Posts", posts_db)

        ok = check_schema(http, "Books", books_ds, BOOKS_SCHEMA)
        ok &= check_schema(http, "Posts", posts_ds, POSTS_SCHEMA)

        if not ok:
            print(
                f"\n{CROSS} Schema does not match. Property names are case-sensitive "
                "and must match docs/notion-setup.md exactly."
            )
            return 1

        print(f"\n{TICK} Both databases match the expected schema.")

        # Resolving these costs a Notion round trip each, on every start. A
        # deployment that starts often — anything serverless — should be told
        # them directly. They are properties of the databases and do not change.
        print(
            "\nOptional, to skip the lookup on every start:\n"
            f"  NOTION_BOOKS_DATA_SOURCE_ID={books_ds}\n"
            f"  NOTION_POSTS_DATA_SOURCE_ID={posts_ds}"
        )

        if args.seed:
            seed(http, books_ds)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.RequestError as exc:
        print(f"{CROSS} Could not reach Notion: {exc}")
        sys.exit(1)
