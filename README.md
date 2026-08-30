# book-club-mini

A self-hosted reading forum for two people working through the same book.

Members record where they are, post progress notes, thoughts and questions as
they read, and reply to one another. Any post anchored ahead of a reader's own
position is blurred for that reader until they choose to reveal it. Notion
provides the database.

Each member runs the full stack on their own machine. There is no shared server
and nothing is deployed.

```text
┌ Piranesi ─────────────────────────────── Ada ─ View as [Ada ▾] ────┐
│ Susanna Clarke        [Books ▾] [Edit book] [Refresh]              │
│                                                                    │
│      Ch 4                        Ch 12 · p.204                     │
│  ────●───────────────────────────────●░░░░░░░░░░░░░░░░░░ Ch 30     │
│    2 days ago                      3h ago      ← blurred for you   │
│                                                                    │
│ [New post]   All 7 · Progress 3 · Thoughts 3 · Questions 1         │
└────────────────────────────────────────────────────────────────────┘
```

## Features

- **Position-aware blurring.** Posts ahead of your reading position are blurred,
  with author, position and timestamp left visible.
- **A shared progress indicator.** One marker per member, calibrated to the
  book's length when known and inferred from activity when not.
- **Four post types.** Progress updates, thoughts, questions, and one level of
  replies.
- **Long-form posts.** Bodies beyond the storage layer's field limit are stored
  intact and loaded on demand.
- **A multi-book library** with one book current at a time.

## Requirements

- Python 3.11 or later
- Node.js 20 or later
- A Notion workspace with two internal integrations

## Getting started

```bash
git clone <repository-url>
cd book-club-mini
./setup.sh
./dev.sh
```

Then open <http://localhost:5173>.

`setup.sh` checks the toolchain, installs dependencies, prompts for
configuration, and validates the Notion workspace before reporting success.

The Notion side must exist first. [docs/notion-setup.md](docs/notion-setup.md)
covers it in about fifteen minutes; [docs/installation.md](docs/installation.md)
covers both installations in detail, including the second member's machine.

## Documentation

| Document | Purpose |
| --- | --- |
| [Overview](docs/overview.md) | The project, its data domain, and where it can grow |
| [Installation](docs/installation.md) | Both installations, configuration, troubleshooting |
| [Notion setup](docs/notion-setup.md) | Workspace, databases, environment files |
| [Architecture](docs/architecture.md) | A guided tour of the codebase |
| [Domain model](docs/domain-model.md) | The domain, specified independently of any technology |
| [Storage backends](docs/storage-backends.md) | Replacing Notion with another database |
| [Decisions](docs/decisions.md) | One entry per pattern, and what would justify removing it |

## Architecture

```text
backend/app/
├── domain/          entities, value objects, policies, services — no I/O
├── ports/           repository and unit-of-work abstractions
├── application/     use cases, feed assembly, caching
├── adapters/
│   ├── memory/      in-memory implementation, used by tests
│   └── notion/      HTTP client, mappers, repositories, unit of work
├── interface/       FastAPI routers, DTOs, error mapping
└── composition.py   the dependency-injection container
```

Dependencies point inward only, enforced by a test over the import graph rather
than by review. Persistence sits behind three abstractions declared next to the
domain, and one contract suite runs against every implementation — which is the
concrete meaning of being able to change database: write one adapter package,
point the container at it, and run that suite.

The frontend keeps all state, derivation and formatting in hooks and pure
functions; components are presentational and untested by design.

## Testing

```bash
cd backend
.venv/bin/python -m pytest                        # full suite
.venv/bin/python -m pytest tests/unit -q          # fast loop
.venv/bin/python scripts/check_coverage.py        # per-package thresholds

cd ../frontend
npm test
npm run coverage
```

No test requires network access. Coverage floors are 100% line and branch on
`domain/` and `application/`, and 90% on `adapters/` and `interface/`.

## Limitations

**There is no authentication.** Each installation declares its member name in
configuration and the backend accepts it. Ownership checks on edit and delete
prevent accidents, not attacks. This suits two people running on their own
machines; exposing the application to a network is a redesign rather than a
deployment.

**Blurring is presentational.** Blurred text is delivered to the browser and is
readable in developer tools. It guards against accidental spoilers, not against
a determined reader.

**Rollback is compensating, not atomic.** Notion provides no transactions, so a
failed multi-step write is undone by replaying inverse operations. A
compensation can itself fail, and a concurrent reader may observe an
intermediate state. Failed compensations are logged with enough detail for
manual repair.

**Request throughput is bounded.** Notion permits roughly three requests per
second per integration. The application is built to that budget: one query per
feed load, a short read-through cache, and no polling. Any change that fetches
per-post data in a loop will exceed it first.

**The Notion workspace must remain single-member.** Inviting a second person to
a free workspace starts a team trial with a block limit. The second reader needs
no Notion access; the integrations are the only writers.

Further limits are listed in [docs/overview.md](docs/overview.md#known-limits).

## Licence

See [LICENSE](LICENSE).
