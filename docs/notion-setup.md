# Notion workspace setup

Everything required on the Notion side, plus the environment configuration that
connects an installation to it.

Perform sections 1–5 once, on the account that owns the workspace. Section 6 is
performed once per installation.

Allow about fifteen minutes.

---

## 1. Create the parent page

Create a Notion page named **Book Club**. Both databases will live inside it.

**Keep the workspace to a single member.** Do not invite the second reader to
Notion. Inviting a second person to a free workspace starts a team trial with a
block limit, and the second reader does not need Notion access — the
integrations are the only writers.

---

## 2. Create two integrations

At <https://www.notion.so/my-integrations>, create **two** internal
integrations:

- `Book Club — <first member>`
- `Book Club — <second member>`

Each requires **read content**, **update content** and **insert content**
capabilities. No user information capabilities are needed.

Two integrations rather than one because Notion applies rate limits per
integration. Separate tokens give each member an independent budget, and either
can be revoked without disturbing the other.

Copy both tokens now — they begin with `ntn_`. Each installation receives
exactly one.

> Treat a token like a password. It grants full read and write access to every
> page shared with its integration. Send it over a private channel, never
> through version control.

---

## 3. Connect the integrations to the page

On the **Book Club** page, choose `•••` → **Connections** → add both
integrations.

Databases created inside the page inherit its connections, so this is done once
per integration rather than once per database.

> A `404` from the Notion API almost always means this step was skipped.
> `verify_notion.py` recognises the case and prints the remedy instead of the
> raw error.

---

## 4. Create the databases

Build both **in the Notion interface** as full-page databases inside **Book
Club**. Creating them through the API is possible, but the create-database
payload changed shape in API version `2025-09-03`, and the interface is faster
and verifiable by eye.

Create **Books** first — the relation on Posts needs a target.

### Books

| Property | Type | Configuration |
| --- | --- | --- |
| `Title` | Title | |
| `Author` | Text | |
| `Status` | Select | Options: `Currently Reading`, `Upcoming`, `Paused`, `Finished` |
| `Total Chapters` | Number | |

A new database's title property is named `Name` by default. **Rename it to
`Title`.**

### Posts

| Property | Type | Configuration |
| --- | --- | --- |
| `Name` | Title | Generated label; never read back by the application |
| `Book` | Relation | Target: **Books**. Turn **off** "Show on Books" |
| `Member` | Select | Leave options empty; created on first write |
| `Type` | Select | Options: `Progress`, `Thought`, `Question`, `Reply` |
| `Body Preview` | Text | |
| `Has Full Body` | Checkbox | |
| `Chapter` | Number | |
| `Page` | Number | |
| `Parent Post ID` | Text | |

**Property names are case-sensitive and must match exactly.** They are constants
in `backend/app/adapters/notion/mappers.py`, and an automated check keeps them
from appearing anywhere else in the codebase.

### Three that commonly go wrong

**The relation must be named `Book`, singular.** Notion names a new relation
after the database it points at, so it is created as `Books`. Rename it.

**Turn off the two-way sync.** When creating the relation, disable "Show on
Books". A synced back-reference adds a property to maintain and provides nothing
the application uses.

**`Parent Post ID` is a plain text property, not a relation.** A self-relation
in Notion creates a synced two-way property, which buys nothing for one-level
replies.

### Leaving `Member` options empty

Notion creates a select option automatically the first time a value is written.
Pre-creating them risks a mismatch between the option text and `MEMBER_NAME`,
which would produce posts attributed to a member the application does not
recognise.

---

## 5. Collect the database identifiers

Open each database as a full page. The URL has this shape:

```text
https://www.notion.so/<workspace>/<optional-title-slug>-<32-hex-characters>?v=<view-id>
```

The database identifier is the 32 hexadecimal characters immediately before
`?v=`. Discard any title slug in front of it.

```text
https://www.notion.so/myspace/Books-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d?v=abc123
                                    └──────── database identifier ────────┘
```

That value is the **database** identifier. Rows actually live on a *data source*
inside the database — a distinction introduced in API version `2025-09-03` — and
the application resolves one to the other once at startup. You never need to
supply a data source identifier yourself.

Record both:

| Database | Environment variable |
| --- | --- |
| Books | `NOTION_BOOKS_DB_ID` |
| Posts | `NOTION_POSTS_DB_ID` |

---

## 6. Configure an installation

Each installation reads `backend/.env`. Create it from the template:

```bash
cp backend/.env.example backend/.env
```

| Variable | Same on both machines? | Value |
| --- | --- | --- |
| `NOTION_TOKEN` | **No** | This member's integration token |
| `NOTION_BOOKS_DB_ID` | Yes | From §5 |
| `NOTION_POSTS_DB_ID` | Yes | From §5 |
| `MEMBER_NAME` | **No** | This member's name, as it should appear on posts |
| `MEMBERS` | Yes | Full roster, comma-separated |

First installation:

```ini
NOTION_TOKEN=ntn_A1b2C3d4E5f6G7h8I9j0
NOTION_BOOKS_DB_ID=1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
NOTION_POSTS_DB_ID=9f8e7d6c5b4a39281706f5e4d3c2b1a0
MEMBER_NAME=Ada
MEMBERS=Ada,Grace
```

Second installation — note that only two lines differ:

```ini
NOTION_TOKEN=ntn_Z9y8X7w6V5u4T3s2R1q0
NOTION_BOOKS_DB_ID=1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
NOTION_POSTS_DB_ID=9f8e7d6c5b4a39281706f5e4d3c2b1a0
MEMBER_NAME=Grace
MEMBERS=Ada,Grace
```

### Rules the application enforces

- **`MEMBER_NAME` must appear in `MEMBERS`.** Startup fails otherwise. An
  installation missing from its own roster cannot render the progress indicator
  and would attribute posts to an unrecognised member.
- **`MEMBERS` must be empty of neither entries nor meaning.** Whitespace around
  names is trimmed; empty entries are discarded.

### A rule the application cannot enforce

**`MEMBERS` must be listed in the same order on both machines.** Reader colours
are assigned by roster index, so a reversed order swaps the two members' colours
between installations. Nothing detects this — agree the exact string once and
paste it into both files.

`backend/.env` is excluded from version control. Never commit it.

---

## 7. Verify

```bash
cd backend
.venv/bin/python scripts/verify_notion.py
```

The script resolves both databases, reports their data source identifiers, and
checks every property by name and type:

```text
Resolving databases

✓ Books: 'Books'
    database_id    1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
    data_source_id 1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d
✓ Posts: 'Posts'
    database_id    9f8e7d6c5b4a39281706f5e4d3c2b1a0
    data_source_id 9f8e7d6c-5b4a-3928-1706-f5e4d3c2b1a0

  Books properties
    ✓ Title           title
    ✓ Author          rich_text
    ✓ Status          select
    ✓ Total Chapters  number

  Posts properties
    ✓ Name            title
    ✓ Book            relation
    ✓ Member          select
    ✓ Type            select
    ✓ Body Preview    rich_text
    ✓ Has Full Body   checkbox
    ✓ Chapter         number
    ✓ Page            number
    ✓ Parent Post ID  rich_text

✓ Both databases match the expected schema.
```

It exits non-zero on any mismatch. Resolve every `✗` before starting the
application.

Optionally create one book so the interface has something to show:

```bash
.venv/bin/python scripts/verify_notion.py --seed
```

Run the verification on **both** machines. It confirms each token independently,
which is the only check that catches an integration connected to the page on one
account but not the other.

---

## 8. Diagnostics

| Symptom | Cause | Remedy |
| --- | --- | --- |
| `404` on a database | Integration not connected to the page | §3 |
| `401 Unauthorized` | Token wrong, truncated or revoked | Recopy from the integrations page |
| `✗ Book missing (expected relation)` | Relation still named `Books` | Rename the property to `Book` |
| `✗ Title missing` | Title property still named `Name` | Rename it to `Title` |
| `✗ … is rich_text, expected select` | Property created with the wrong type | Change the type in Notion |
| `database has no data sources` | The identifier is a page, not a database | Recheck §5 |
| Posts attributed to an unexpected member | `MEMBER_NAME` differs between machines | Align the values |
| Members show the wrong colours | `MEMBERS` ordered differently | Align the roster order |

### Editing rows directly in Notion

Both databases remain fully usable through the Notion interface, and the
application tolerates hand edits by design: an unrecognised `Status` reads as
`Upcoming`, a missing number reads as absent, and a `Progress` row with its
chapter cleared degrades to a `Thought` rather than faulting the feed.

Two edits are still worth avoiding:

- **Clearing `Has Full Body` on a post that has a body block** leaves the full
  text unreachable through the application.
- **Editing `Parent Post ID`** can orphan a reply. Orphaned replies are dropped
  from the feed rather than shown at the top level.

Deleting rows in Notion is safe. The application already treats deletion as
archival, and archived rows are excluded from queries.
