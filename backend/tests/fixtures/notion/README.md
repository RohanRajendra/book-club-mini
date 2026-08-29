# Real Notion response fixtures

`phase-1-notion-and-scaffold.md` §1.6 and `phase-4-notion-adapter.md` §4.4 require
the mapper tests to run against **real recorded Notion responses**, not
hand-written payloads: "hand-written approximations are how a suite goes green
against an API that would reject it."

These files are not committed yet because the Notion workspace does not exist
yet. `tests/integration/test_mappers.py` skips with a pointer to this file until
they are here.

## Capturing them

With `backend/.env` filled in and the databases created (see
`docs/notion-setup.md`):

```
cd backend
.venv/bin/python scripts/verify_notion.py --seed          # one row to query
.venv/bin/python scripts/capture_fixtures.py
```

That writes the five files below, scrubbing workspace and user IDs:

| File | Source |
|---|---|
| `database.json` | `GET /v1/databases/{books db id}` |
| `data_source.json` | `GET /v1/data_sources/{books ds id}` |
| `query.json` | `POST /v1/data_sources/{posts ds id}/query` — needs ≥2 rows |
| `page_create.json` | `POST /v1/pages` |
| `block_children.json` | `GET /v1/blocks/{page id}/children` |

`query.json` wants two posts with different shapes to be worth having: one short
top-level post and one long reply. Post them in the app, or let
`capture_fixtures.py` create them with `--seed-posts`.

Then re-run `pytest tests/integration/test_mappers.py` and the skips become
assertions.
