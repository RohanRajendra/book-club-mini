# Phase 1 — Notion setup and scaffold

**Goal:** two correctly shaped Notion databases, two integrations, a project
skeleton, and a test harness that runs green on an empty suite.

**Produces:** working `pytest` and `vitest` commands, a passing verify script.

## 1.1 Owner tasks (human)

The agent cannot do these. Walk the owner through them.

1. Create a Notion page called **Book Club**. Keep the workspace **solo** — do not
   invite the second member. Adding a member to a free workspace triggers a
   1000-block team trial limit, and she does not need Notion access.
2. At `notion.so/my-integrations`, create **two** internal integrations:
   `Book Club — <name A>` and `Book Club — <name B>`. Each needs read, update, and
   insert content capabilities. Rate limits are per integration, so two tokens give
   each member their own budget and either can be revoked alone.
3. On the **Book Club** page → `•••` → **Connections** → add both integrations.
   Databases created inside the page inherit the connections.
4. Copy both tokens. Each member's `.env` gets one.

## 1.2 Create the databases

Build these **in the Notion UI** as full-page databases inside **Book Club**.
Creating them through the API is possible, but the create-database payload changed
shape in `2025-09-03` and the UI is faster and verifiable by eye.

Create `Books` first — the `Posts.Book` relation needs a target.

**Books:** `Title` (Title), `Author` (Text), `Status` (Select — `Currently Reading`,
`Upcoming`, `Paused`, `Finished`), `Total Chapters` (Number).

**Posts:** `Name` (Title), `Book` (Relation → Books, **turn off "Show on Books"**),
`Member` (Select, leave options empty — the API creates them on first write),
`Type` (Select — `Progress`, `Thought`, `Question`, `Reply`), `Body Preview` (Text),
`Has Full Body` (Checkbox), `Chapter` (Number), `Page` (Number),
`Parent Post ID` (Text).

Names must match exactly, including capitalisation. They become constants in
`adapters/notion/mappers.py`.

Database IDs come from the URL: in `notion.so/<workspace>/<32-char-id>?v=<view>`,
the database ID is the segment before `?v=`.

## 1.3 Scaffold

Create the tree from `02-architecture.md` §Layers, with every package containing an
`__init__.py` and nothing else yet. Empty packages now beat moving files in Phase 5.

```
bookclub/
├── backend/
│   ├── app/            # per 02-architecture.md
│   ├── tests/
│   │   ├── unit/ contract/ integration/ api/ architecture/
│   │   ├── fixtures/notion/
│   │   ├── builders.py
│   │   └── conftest.py
│   ├── scripts/verify_notion.py
│   ├── pyproject.toml
│   ├── .env.example
│   └── .env            # gitignored
├── frontend/           # created in Phase 7
├── docs/decisions.md   # pattern justifications, per 02
├── dev.sh
└── .gitignore
```

`.gitignore` and `.env.example` land in the same commit that creates `.env`.

`.env.example`:

```
NOTION_TOKEN=ntn_xxx
NOTION_BOOKS_DB_ID=
NOTION_POSTS_DB_ID=
MEMBER_NAME=
MEMBERS=Name A,Name B
```

`pyproject.toml` configures pytest: `asyncio_mode = "auto"`, testpaths, and the
`fake_only` marker registered so `--strict-markers` passes.

## 1.4 Config, test-first

The first red-green cycle of the project. Write these tests before `config.py`:

```
test_settings_parses_members_into_list
test_settings_strips_whitespace_around_member_names
test_settings_rejects_member_name_absent_from_members
test_settings_rejects_empty_members
test_settings_rejects_missing_notion_token
```

The third test is the one that matters. An installation whose `MEMBER_NAME` is not
in its own `MEMBERS` roster renders a broken spine and attributes posts to a member
the app does not know about — fail at startup instead.

Then write `Settings`.

## 1.5 The verify script

`scripts/verify_notion.py`, standalone, `httpx` only. Not part of the app and not
under test — it is an operator tool.

1. Read env vars; fail with a readable message naming any that are missing.
2. `GET /v1/databases/{id}` for each database with
   `Authorization: Bearer <token>` and `Notion-Version: 2025-09-03`.
3. Print each database title and its resolved `data_sources[0].id`.
4. `GET /v1/data_sources/{ds}` and compare properties against §1.2. Print a
   per-property ✓ / ✗ table.
5. Exit non-zero on any mismatch.

On a 404, print: *"Notion returned 404. The integration is probably not connected
to the Book Club page — open the page, ••• → Connections, and add it."* That is
the single most common Notion API mistake and the raw error does not say so.

Add `--seed` to create one book with `Status: Currently Reading`:

```json
POST /v1/pages
{
  "parent": {"type": "data_source_id", "data_source_id": "<books ds id>"},
  "properties": {
    "Title":  {"title": [{"text": {"content": "Test Book"}}]},
    "Status": {"select": {"name": "Currently Reading"}}
  }
}
```

Note the parent is the **data source** ID.

## 1.6 Capture fixtures

While the script is working, save real Notion responses to
`tests/fixtures/notion/`: a database response, a data source response, a query
response with two rows, a page-create response, and a block-children response.
Scrub workspace and user IDs.

Do this now, with a live API in hand. Phase 4's integration tests depend on real
payload shapes, and hand-written approximations are how a suite goes green against
an API that would reject it.

## 1.7 Architecture tests

Write these before there is anything to violate. They will pass trivially today and
start earning their keep in Phase 5.

```
test_domain_does_not_import_application_interface_or_adapters
test_application_does_not_import_adapters_or_interface
test_notion_property_names_appear_only_in_adapters_notion
```

Walk the import graph with `ast`. A dozen lines each.

## Acceptance checks

- [ ] `pytest` runs and passes with the config and architecture tests only
- [ ] `pytest --cov=app` reports coverage without error
- [ ] `python scripts/verify_notion.py` exits 0 and prints two data source IDs
- [ ] Every expected property shows ✓
- [ ] `--seed` creates a visible row in Notion
- [ ] A deliberately wrong token produces the readable connection message, not a
      stack trace
- [ ] Five real Notion fixtures are committed
- [ ] `.env` is gitignored; `.env.example` is committed
