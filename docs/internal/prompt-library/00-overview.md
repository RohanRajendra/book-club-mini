# Book Club — Build Plan

Read this file first, then `01-ux-spec.md`, `02-architecture.md`, and
`03-testing-strategy.md` before starting Phase 1. The phase files assume all four.

## What we are building

A two-person book club forum. Members post progress updates, thoughts, and
questions as they read a book, and reply to each other. Posts that run ahead of
your reading position are blurred. Notion is the database.

Each member runs their **own copy** of the app on their own machine, both pointed
at the same Notion workspace. There is no shared server and no deployment.

## Locked decisions

| Area | Decision |
|---|---|
| Backend | FastAPI, Python 3.11+ |
| Frontend | React + Vite, JavaScript |
| Data store | Notion REST API, `Notion-Version: 2025-09-03` |
| Notion plan | Free. Workspace stays **solo** — the second member is never invited |
| Topology | Two installations, two Notion integrations, one shared Book Club page |
| Identity | `MEMBER_NAME` in each `.env`. No login, no passcode, no member picker |
| Post types | `Progress`, `Thought`, `Question`, `Reply` |
| Replies | Flat. One level. No replies to replies |
| Position | Chapter + optional page. Chapter dominates, page is a tiebreaker |
| Spoilers | Blur with reveal-on-click. Never hide. Metadata always visible |
| Books | Multiple, one `Currently Reading`. Title is the only required field |
| Spine scale | Real if total chapters known, otherwise inferred from posts |
| Post body | ≤1900 chars in a Notion property (the feed preview); longer bodies also written to one page block |
| Edit / delete | Own posts only |
| Refresh | Window focus + manual button. No polling |
| Architecture | Layered: domain → application → adapters. Repository + unit-of-work ports, Result objects, explicit DI container |
| Testing | TDD throughout. Backend: full unit coverage plus contract and integration suites. Frontend: hooks and helpers only, no component tests |

## Non-goals

Deployment, real authentication, notifications, search, reactions, ratings, cover
images, reading streaks, multi-club support, nested threading, real-time updates.
Do not build these. Do not add dependencies beyond those named in the phase files.

## The three Notion facts that break builds

**1. Data sources, not databases.** Since API version `2025-09-03`, a database is a
container holding one or more data sources, and rows live on the data source.
Query with `POST /v1/data_sources/{data_source_id}/query`. Create rows with
`POST /v1/pages` and `parent: {"type": "data_source_id", "data_source_id": "..."}`.
The ID in a Notion URL is the **database** ID; resolve it once at startup via
`GET /v1/databases/{id}` → `data_sources[0].id`. The two ID types are not
interchangeable.

**2. Roughly 3 requests/second per integration**, 429 on overage. Every Notion call
goes through one rate-limited client. A feed load must cost exactly one request.

**3. No transactions.** See the unit-of-work section of `02-architecture.md`.

## Notion schema

Two databases in one parent page, both connected to both integrations.

**Books** — `Title` (title), `Author` (text), `Status` (select: `Currently Reading`,
`Upcoming`, `Paused`, `Finished`), `Total Chapters` (number).

**Posts** — `Name` (title, generated label, never parsed), `Book` (relation → Books,
one-way), `Member` (select), `Type` (select: `Progress`, `Thought`, `Question`,
`Reply`), `Body Preview` (text, ≤1900), `Has Full Body` (checkbox), `Chapter`
(number), `Page` (number), `Parent Post ID` (text, empty for top-level).

Timestamps come from the page object's built-in `created_time` and
`last_edited_time`. Do not add timestamp properties.

Schema notes the agent will otherwise get wrong:

- `Parent Post ID` is **plain text, not a self-relation**. A self-relation creates a
  synced two-way property that buys nothing for flat replies.
- `Book` **is** a real relation, so the owner can browse posts grouped by book
  inside Notion. Filter with `{"property": "Book", "relation": {"contains": id}}`.
- Replies **copy** their parent's chapter and page at creation. This keeps spoiler
  evaluation join-free.
- **1900, not 2000.** Notion's rich text property caps at 2000; the margin keeps
  truncation from colliding with the limit.
- `Has Full Body` exists so the feed never has to guess whether a 1900-character
  preview was truncated. Without it you need a request per post to find out.

## Phase order

Every phase is test-driven and ends green. Do not begin a phase until the previous
one's acceptance checks pass.

| Phase | File | Produces |
|---|---|---|
| 1 | `phase-1-notion-and-scaffold.md` | Notion databases, repo skeleton, test harness |
| 2 | `phase-2-domain-core.md` | Pure domain. Zero I/O, 100% covered |
| 3 | `phase-3-ports-and-fakes.md` | Repository and unit-of-work ports, in-memory adapter, contract suite |
| 4 | `phase-4-notion-adapter.md` | Notion adapter passing the same contract suite |
| 5 | `phase-5-application-services.md` | Use cases, feed assembly, caching decorator |
| 6 | `phase-6-http-api.md` | FastAPI routers, DTOs, container wiring |
| 7 | `phase-7-frontend.md` | React app, hook tests |
| 8 | `phase-8-polish-and-handoff.md` | Setup script, README, second-machine install |

Phases 2 and 3 produce no user-visible behaviour and involve no network. That is
deliberate: the domain and its ports are the parts that must be right before
anything touches Notion, and they are the parts a database swap would preserve.
