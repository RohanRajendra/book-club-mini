# Setting up the Notion side

Do this once, on the account that owns the workspace. It takes about ten minutes.
`setup.sh` handles everything after it.

## 1. The page

Create a Notion page called **Book Club**.

**Keep the workspace solo.** Do not invite the second member. Adding a member to
a free workspace triggers a 1000-block team trial limit, and she does not need
Notion access — the integrations are the only writers.

## 2. Two integrations

At [notion.so/my-integrations](https://www.notion.so/my-integrations), create
**two** internal integrations:

- `Book Club — <name A>`
- `Book Club — <name B>`

Each needs **read**, **update** and **insert content** capabilities.

Two tokens rather than one because rate limits are per integration, so each
member gets their own budget, and either can be revoked without disturbing the
other.

Copy both tokens now. Each member's `.env` gets one.

## 3. Connect them

On the **Book Club** page → `•••` → **Connections** → add both integrations.

Databases created inside the page inherit these connections.

> A 404 from Notion almost always means this step was missed.
> `verify_notion.py` says so explicitly rather than showing the raw error.

## 4. The databases

Build these **in the Notion UI** as full-page databases inside **Book Club**.
Creating them through the API is possible, but the create-database payload
changed shape in `2025-09-03` and the UI is faster and verifiable by eye.

Create **Books** first — the `Posts.Book` relation needs a target.

### Books

| Property | Type | Options |
|---|---|---|
| `Title` | Title | — |
| `Author` | Text | — |
| `Status` | Select | `Currently Reading`, `Upcoming`, `Paused`, `Finished` |
| `Total Chapters` | Number | — |

A new database's title property is called `Name` by default. **Rename it to
`Title`.**

### Posts

| Property | Type | Notes |
|---|---|---|
| `Name` | Title | Generated label, never parsed |
| `Book` | Relation → Books | Turn **off** "Show on Books" |
| `Member` | Select | Leave the options empty; the API creates them on first write |
| `Type` | Select | `Progress`, `Thought`, `Question`, `Reply` |
| `Body Preview` | Text | |
| `Has Full Body` | Checkbox | |
| `Chapter` | Number | |
| `Page` | Number | |
| `Parent Post ID` | Text | Plain text, **not** a self-relation |

**Names must match exactly, including capitalisation.** They are constants in
`backend/app/adapters/notion/mappers.py`, and an architecture test keeps them
from appearing anywhere else.

Two that catch people out:

- **The relation is `Book`, singular.** Notion names a new relation after the
  database it points at, so it will be created as `Books`. Rename it.
- **`Parent Post ID` is plain text.** A self-relation creates a synced two-way
  property that buys nothing for flat replies.

## 5. The database IDs

Open each database as a full page. The URL looks like:

```
notion.so/<workspace>/<32-char-id>?v=<view-id>
```

The database ID is the segment before `?v=`. There may be a title slug in front
of it; you want the 32 hex characters.

That ID is the **database** ID. Rows actually live on a *data source* inside it,
and the app resolves one to the other at startup — you never need the data
source ID yourself.

## 6. Check it

```
cd backend
.venv/bin/python scripts/verify_notion.py
```

It prints a ✓/✗ table for every property and exits non-zero on any mismatch.
Get it fully green before starting the app.

Optional, to have something to look at:

```
.venv/bin/python scripts/verify_notion.py --seed
```

## 7. The second machine

She clones the repo and runs `./setup.sh`. It asks for her token, the two
database IDs, her name, and the roster.

The roster must be **in the same order on both machines** — reader colours are
assigned by position, so a swapped order swaps the two members' colours.
