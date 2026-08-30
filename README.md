# book-club-mini

A two-person book club forum. Post progress, thoughts and questions as you read;
reply to each other; anything ahead of your reading position is blurred until
you choose to see it. Notion is the database.

Each member runs their own copy on their own machine, both pointed at the same
Notion workspace. There is no shared server and nothing is deployed.

```text
┌ Piranesi ─────────────────────────────── Rohan ─ View as [Rohan ▾] ┐
│ Susanna Clarke        [Books ▾] [Edit book] [Refresh]              │
│                                                                    │
│      Ch 4                        Ch 12 · p.204                     │
│  ────●───────────────────────────────●░░░░░░░░░░░░░░░░░░ Ch 30     │
│    2 days ago                      3h ago      ← blurred for you   │
│                                                                    │
│ [New post]   All 7 · Progress 3 · Thoughts 3 · Questions 1         │
└────────────────────────────────────────────────────────────────────┘
```

## Setup

**First machine.** Do the Notion side once — see
[docs/notion-setup.md](docs/notion-setup.md) — then:

```bash
./setup.sh
./dev.sh
```

**Second machine.** Clone, run `./setup.sh`, and give it: your own integration
token, the two database IDs, your name, and the roster. Then `./dev.sh`.

Open <http://localhost:5173>.

If anything is wrong with the Notion side, this tells you exactly what:

```bash
cd backend && .venv/bin/python scripts/verify_notion.py
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest                                   # everything
.venv/bin/python -m pytest tests/unit -q                     # the fast loop
.venv/bin/python -m pytest --cov=app --cov-branch
.venv/bin/python scripts/check_coverage.py                   # per-package gates

cd ../frontend
npm test
npm run coverage
```

Coverage floors: 100% line **and branch** on `app/domain` and `app/application`,
≥90% on `app/adapters` and `app/interface`, ≥90% on frontend hooks and lib.
React components are not tested — see
[docs/decisions.md](docs/decisions.md#deliberately-not-added).

## Five things to be straight about

**There is no authentication.** Each installation declares who it is in `.env`
and the server believes it. The ownership checks on edit and delete prevent
accidents, not attacks. That is fine between two people running on their own
machines. It would not survive being put on the internet, and putting it there
is a redesign, not a deployment.

**Blur is not secrecy.** Blurred post text is sent to the browser and is readable
in devtools. It is a courtesy against accidental spoilers, nothing more.

**The Notion workspace must stay solo.** Do not invite the second member to
Notion. Adding a member to a free workspace triggers a 1000-block team trial
limit, and the integrations are the only writers.

**Rollback is compensating, not atomic.** Notion has no transactions.
`NotionUnitOfWork` undoes a failed multi-step write by replaying inverse
operations. A compensation can itself fail, and a concurrent reader can observe
an intermediate state. Failed compensations are logged at ERROR with enough
detail to repair by hand.

**The rate limit is the real ceiling.** Roughly 3 requests/second per
integration. The app is built around it: one data-source query per feed load
plus one book read, a 20-second cache, no polling. Any future feature that
fetches per-post data in a loop breaks this first.

## Known limits

Written down rather than fixed:

- A feed caps at 500 posts per book. Past that, older posts stop appearing. The
  fix is date-bounded queries, not a bigger cap.
- Editing a post does not update the positions copied onto its replies. A reply's
  position is a snapshot of where the conversation started.
- No full-text search. Notion's search API is workspace-wide and filters poorly;
  search in Notion directly.
- Positions assume both members use the same chapter numbering. Page numbers may
  differ between editions, which is why the spoiler rule leans on chapter and
  only uses the page as a tiebreaker within one.
- Only the first data source of each database is used.
- The two installations do not know about each other. No notifications and no
  real-time updates; you find out she posted by refreshing.
- Reader colours come from position in `MEMBERS`, so both machines must list the
  roster in the same order.

## How it is put together

```text
backend/app/
├── domain/        entities, values, policies, services. Zero I/O
├── ports/         BookRepository, PostRepository, UnitOfWork
├── application/   use cases, feed assembly, caching decorator
├── adapters/
│   ├── memory/    in-memory implementations, used by tests
│   └── notion/    HTTP client, mappers, repositories, compensating UoW
├── interface/     FastAPI routers, DTOs, error map
└── composition.py the DI container
```

Dependencies point inward only, and an architecture test enforces it rather than
relying on discipline. The same contract suite runs against both the in-memory
and the Notion adapter, which is the concrete meaning of "we could swap the
database": implement the three ports in a new package, point the container at
it, and run that suite.

[docs/decisions.md](docs/decisions.md) has one entry per pattern — what it is,
the requirement that justified it, and what would have to change for it to go.
[docs/spec-deltas.md](docs/spec-deltas.md) records every place this build
diverges from `prompt-library/`, which is left untouched as the reference.
