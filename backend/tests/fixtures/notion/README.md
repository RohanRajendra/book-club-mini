# Recorded Notion responses

The mapper tests in `tests/integration/test_mappers.py` run against **real
recorded responses** rather than hand-written payloads. Hand-written
approximations are how a suite goes green against an API that would reject it,
so those tests skip rather than substitute one when these files are absent.

## Capturing

With `backend/.env` configured and the databases created — see
[docs/notion-setup.md](../../../../docs/notion-setup.md):

```bash
cd backend
.venv/bin/python scripts/verify_notion.py --seed      # one book to query
.venv/bin/python scripts/capture_fixtures.py --seed-posts
```

That writes the five files below, scrubbing user identity:

| File | Source |
| --- | --- |
| `database.json` | `GET /v1/databases/{books database id}` |
| `data_source.json` | `GET /v1/data_sources/{books data source id}` |
| `query.json` | `POST /v1/data_sources/{posts data source id}/query` |
| `page_create.json` | A book row as returned by `POST /v1/pages` |
| `block_children.json` | `GET /v1/blocks/{page id}/children` |

`query.json` needs at least two posts of different shapes to be worth having:
one short top-level post and one long reply. `--seed-posts` creates both, along
with the body block that `block_children.json` records.

Omit `--seed-posts` to capture from content that already exists.

## Scrubbing

Only identity-bearing keys are removed: `avatar_url`, `person`, `email`, and any
object whose `object` field is `user` or `bot`.

Select option values are deliberately **preserved**. An earlier version blanked
every key named `name`, which includes the `name` inside a select value — every
`Type`, `Status` and `Member` became `"scrubbed"`, the mapper silently fell back
to its defaults, and every shape assertion still passed.
`test_a_real_select_value_maps_to_its_enum_member` exists to catch exactly that,
by asserting the mapped values are *recognised* enum members rather than merely
present.

Page and block identifiers are kept. The mapper reads them, and they are
meaningless outside the workspace they came from.

## Refreshing

Recapture whenever the Notion schema changes or the API version is raised. The
files are committed so the suite runs without network access.
