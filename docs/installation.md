# Installation

This guide covers both installations: the first, run by whoever owns the Notion
workspace, and the second, run by the other member.

The Notion workspace must exist before either installation will start. If it
does not yet, work through [notion-setup.md](notion-setup.md) first and return
here.

---

## Requirements

| Requirement | Minimum | Check |
| --- | --- | --- |
| Python | 3.11 | `python3 --version` |
| Node.js | 20 | `node --version` |
| Notion integration token | one per member | starts with `ntn_` |
| Notion database IDs | two, shared | see [notion-setup.md](notion-setup.md) |

Nothing else is needed. There is no container runtime, no database server and no
deployment target.

---

## Quick start

```bash
git clone <repository-url>
cd book-club-mini
./setup.sh
./dev.sh
```

Then open <http://localhost:5173>.

`setup.sh` verifies the toolchain, installs both dependency sets, prompts for
configuration, writes `backend/.env`, and validates the Notion workspace before
reporting success. `dev.sh` runs both servers; one `Ctrl-C` stops both.

The remainder of this document explains each step, for the cases where the
script is not appropriate or something fails.

---

## First installation

### 1. Install dependencies

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
cd backend && .venv/bin/python -m pip install -e ".[dev]" && cd ..

cd frontend && npm install && cd ..
```

The backend installs in editable mode with its development extras, which brings
in the test toolchain. There is no separate production install path; the
application is only ever run locally.

### 2. Configure

Copy the template and fill it in:

```bash
cp backend/.env.example backend/.env
```

| Variable | Required | Description |
| --- | --- | --- |
| `NOTION_TOKEN` | yes | This installation's integration token |
| `NOTION_BOOKS_DB_ID` | yes | Books database ID, 32 hex characters |
| `NOTION_POSTS_DB_ID` | yes | Posts database ID, 32 hex characters |
| `MEMBER_NAME` | yes | Who this installation posts as |
| `MEMBERS` | yes | Full roster, comma-separated |

A complete example:

```ini
NOTION_TOKEN=ntn_A1b2C3d4E5f6G7h8I9j0
NOTION_BOOKS_DB_ID=1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
NOTION_POSTS_DB_ID=9f8e7d6c5b4a39281706f5e4d3c2b1a0
MEMBER_NAME=Ada
MEMBERS=Ada,Grace
```

Three constraints on these values:

- **`MEMBER_NAME` must appear in `MEMBERS`.** The application refuses to start
  otherwise. An installation missing from its own roster cannot render the
  progress indicator and would attribute posts to a member the application does
  not recognise.
- **`MEMBERS` must be listed in the same order on both machines.** Reader
  colours are assigned by roster index, so a reversed order swaps the two
  members' colours between installations.
- **The database IDs are identical on both machines.** The tokens are not.

`backend/.env` is excluded from version control. Do not commit it.

### 3. Verify the workspace

```bash
cd backend
.venv/bin/python scripts/verify_notion.py
```

This resolves both databases, prints their data source identifiers, and checks
every expected property by name and type:

```text
✓ Books: 'Books'
    database_id    1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
    data_source_id 1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d

  Posts properties
    ✓ Name            title
    ✓ Book            relation
    ✓ Member          select
    ...

✓ Both databases match the expected schema.
```

It exits non-zero on any mismatch. Resolve every `✗` before starting the
application — a schema mismatch surfaces later as a confusing runtime error.

Optionally seed one book so the interface has something to display:

```bash
.venv/bin/python scripts/verify_notion.py --seed
```

### 4. Run

```bash
./dev.sh
```

| Service | URL |
| --- | --- |
| Interface | <http://localhost:5173> |
| API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |
| Health | <http://localhost:8000/api/health> |

To run the two services separately — useful when attaching a debugger:

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

---

## Second installation

The second member repeats the same steps on their own machine. Only the
configuration differs.

### What the second member needs

Provide these four things over a private channel:

1. **Their own integration token.** Not a copy of the first member's — separate
   tokens give each member an independent rate-limit budget and allow either to
   be revoked alone. Create the second integration as described in
   [notion-setup.md](notion-setup.md) §2.
2. **Both database IDs.** Identical to the first installation's.
3. **The exact roster string,** character for character, in the same order.
4. **Their own name,** spelled exactly as it should appear on their posts.

### Setup

```bash
git clone <repository-url>
cd book-club-mini
./setup.sh
```

The script prompts for each value and writes `backend/.env` with restrictive
permissions.

### Confirming the pair works

Run through these together, once. They exercise the parts that only fail when
two installations are involved.

| Check | Expected |
| --- | --- |
| Second member opens the app | Their name in the header; both names in the **View as** control |
| Second member posts progress | First member refreshes and sees their marker move |
| First member posts ahead of them | Second member sees it blurred, naming the correct chapter |
| Second member replies to a blurred post | Reply composes without revealing the parent's text |
| Both post within a few seconds | Neither receives a rate-limit error |
| Either uses **View as** | Blur state changes; new posts remain attributed to the actual author |

---

## Configuration reference

### Environment

Loaded from `backend/.env` by `pydantic-settings`. Real environment variables
take precedence over file contents, which is convenient for one-off overrides:

```bash
MEMBER_NAME=Grace ./dev.sh
```

Validation happens at startup, not at first request. A missing or inconsistent
value fails immediately with a message naming the field.

### Ports

| Port | Service | Where to change |
| --- | --- | --- |
| 8000 | Backend | `dev.sh`, and the proxy target in `frontend/vite.config.js` |
| 5173 | Frontend | `frontend/vite.config.js` |

Both must change together: the frontend reaches the backend through a `/api`
proxy declared in the Vite configuration, which is why the backend carries no
CORS middleware.

---

## Verification

```bash
cd backend
.venv/bin/python -m pytest                        # full suite
.venv/bin/python -m pytest tests/unit -q          # fast loop, under two seconds
.venv/bin/python -m pytest --cov=app --cov-branch
.venv/bin/python scripts/check_coverage.py        # per-package thresholds

cd ../frontend
npm test
npm run coverage
```

No network access is required by any test. The Notion adapter is exercised
against recorded responses and a stateful stub.

Three tests are skipped by design. They cover true transactional rollback, which
the Notion adapter cannot provide; they run against the in-memory adapter and
are replaced by compensation tests for Notion.

---

## Troubleshooting

### `404` from Notion

The integration is almost certainly not connected to the parent page. Open the
page in Notion, choose `•••` → **Connections**, and add the integration.
Databases inherit connections from the page containing them, so this must be
done once per integration.

`verify_notion.py` detects this case and prints the remedy rather than the raw
error.

### `401 Unauthorized`

The token is wrong, truncated or revoked. Copy it again from
<https://www.notion.so/my-integrations>.

### Startup fails with a validation error

`MEMBER_NAME` is missing from `MEMBERS`, `MEMBERS` is empty, or a required
variable is unset. The message names the field. Check for a trailing comma or a
stray space in the roster.

### A property shows `✗` in the verify output

The name or type does not match. Notion property names are case-sensitive.

The most common instance: the relation on Posts must be named `Book`, singular.
Notion names a new relation after the database it points at, so it is created as
`Books` and needs renaming.

### CORS errors in the browser console

The Vite proxy is not routing `/api`. Confirm the backend is listening on 8000
and that `frontend/vite.config.js` still contains the proxy entry. Adding CORS
middleware to the backend is the wrong fix and an automated check rejects it.

### `wait: -n: invalid option` from `dev.sh`

An older `bash` is being used than the script expects. The script avoids this
construct; if a modified copy reintroduces it, replace `wait -n` with `wait`.

### Rate limiting under normal use

Notion allows roughly three requests per second per integration, and the client
stays below that deliberately. Sustained `429` responses with two members
usually indicate a change that fetches per-post data in a loop. The backend logs
every outbound request with its path and elapsed time:

```text
INFO app.adapters.notion.http notion POST /data_sources/.../query -> 200 in 272ms
```

A single feed load should produce one query plus at most one book read.
