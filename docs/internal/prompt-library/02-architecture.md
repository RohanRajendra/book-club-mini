# 02 — Architecture

## Principle

Every abstraction in this codebase must be traceable to a stated requirement:
either a testability requirement from `03-testing-strategy.md`, or the stated goal
of being able to swap Notion for another database. An abstraction that serves
neither is ceremony — delete it.

Each pattern below carries its justification. If the agent adds a pattern not
listed here, it must record the same kind of justification in
`docs/decisions.md`. If it cannot, it should not add it.

## Layers

```
┌─ interface ──────────────────────────────────────────┐
│  FastAPI routers, request/response DTOs, error map   │
├─ application ────────────────────────────────────────┤
│  Use cases, feed assembly, caching decorator         │
├─ domain ─────────────────────────────────────────────┤
│  Entities, value objects, policies. Zero I/O         │
├─ ports (owned by domain) ────────────────────────────┤
│  BookRepository, PostRepository, UnitOfWork          │
├─ adapters ───────────────────────────────────────────┤
│  Notion: HTTP client, mappers, repositories, UoW     │
│  InMemory: same ports, used by tests                 │
└──────────────────────────────────────────────────────┘
```

Dependencies point inward only. The domain imports nothing from application,
interface, or adapters. The application imports domain and ports, never adapters.
Enforce it with an import-linting test (see `03`, §Architecture tests) rather than
by discipline.

```
backend/
├── app/
│   ├── domain/
│   │   ├── entities.py        Book, Post
│   │   ├── values.py          Position, MemberName, BookId, PostId, PostType
│   │   ├── policies.py        SpoilerPolicy (+ ChapterFirstSpoilerPolicy)
│   │   ├── services.py        PositionResolver, BodySplitter, ScaleCalculator
│   │   ├── errors.py          Domain error taxonomy
│   │   └── result.py          Result, Ok, Err
│   ├── ports/
│   │   ├── repositories.py    BookRepository, PostRepository (ABCs)
│   │   └── unit_of_work.py    UnitOfWork (ABC)
│   ├── application/
│   │   ├── use_cases/         One module per use case
│   │   ├── feed.py            FeedAssembler
│   │   └── caching.py         CachingFeedQuery decorator
│   ├── adapters/
│   │   ├── memory/            In-memory implementations of every port
│   │   └── notion/
│   │       ├── http.py        NotionHttpClient: rate limit, retry, errors
│   │       ├── ids.py         database_id → data_source_id resolution
│   │       ├── mappers.py     BookMapper, PostMapper
│   │       ├── rich_text.py   Chunking and reading helpers
│   │       ├── repositories.py
│   │       └── unit_of_work.py
│   ├── interface/
│   │   ├── routers/
│   │   ├── schemas.py         Pydantic DTOs — separate from domain entities
│   │   └── errors.py          Domain error → HTTP status mapping
│   ├── composition.py         The DI container
│   ├── config.py              Settings
│   └── main.py
└── tests/
```

## Pattern register

### Repository — `ports/repositories.py`

*Justification: the database-swap goal, and it is what lets every application test
run against an in-memory fake instead of HTTP.*

Two abstract base classes. Methods take and return **domain entities**, never
Notion dicts. Notion's property shapes stop at the mapper.

```python
class BookRepository(ABC):
    async def list_all(self) -> list[Book]
    async def get(self, book_id: BookId) -> Book | None
    async def add(self, book: Book) -> Book
    async def update(self, book: Book) -> Book

class PostRepository(ABC):
    async def list_for_book(self, book_id: BookId) -> list[Post]
    async def get(self, post_id: PostId) -> Post | None
    async def add(self, post: Post, full_body: str | None) -> Post
    async def update(self, post: Post, full_body: str | None) -> Post
    async def archive(self, post_id: PostId) -> None
    async def get_full_body(self, post_id: PostId) -> str
```

`full_body` is a separate parameter rather than a field on `Post` because the
domain entity carries the preview and a `has_full_body` flag; the full text is a
lazily-fetched detail. Keeping it out of the entity is what stops the feed from
accidentally loading bodies.

### Unit of work — `ports/unit_of_work.py`

*Justification: two operations in this app are multi-step and must not half-apply —
creating a long post (page, then block) and deleting a post (post, then each
reply). It is also the correct seam for a future SQLite adapter.*

```python
class UnitOfWork(ABC):
    books: BookRepository
    posts: PostRepository
    async def __aenter__(self) -> "UnitOfWork"
    async def __aexit__(self, *exc) -> None    # rollback if exc, else nothing
    async def commit(self) -> None
    async def rollback(self) -> None
```

**Read this part carefully.** Notion has no transactions. There is no commit point
and no server-side rollback. `NotionUnitOfWork` therefore implements rollback as
**compensating operations**: as each write succeeds it pushes an inverse operation
onto a stack, and `rollback()` replays that stack in reverse.

| Forward operation | Compensation |
|---|---|
| Create page | Archive page |
| Append block | Delete block |
| Update page properties | Restore captured previous properties |
| Archive page | Un-archive page |

This is best-effort, not atomic. A compensation can itself fail, and a concurrent
reader can observe an intermediate state. Both are acceptable for two people, and
both must be stated in the class docstring and the README. Log every failed
compensation at ERROR with enough detail to repair by hand.

`InMemoryUnitOfWork` implements real rollback by snapshotting state on enter, so
the contract tests exercise genuine transactional semantics against the fake and
compensating semantics against Notion. Where the two legitimately differ, the
contract suite marks the test as fake-only and says why.

`commit()` on the Notion adapter clears the compensation stack — writes are already
durable by then. That is not a bug; document it.

### Result objects — `domain/result.py`

*Justification: use cases have expected failures — a missing book, a reply to a
reply, an oversized body. Exceptions for expected outcomes make TDD assertions
awkward and hide the failure set from the type signature.*

```python
Result = Ok[T] | Err[DomainError]
```

Generic, frozen dataclasses, with `is_ok()`, `unwrap()`, `unwrap_err()`, and `map()`.
Every use case returns `Result`. Exceptions are reserved for genuine faults:
network failure, misconfiguration, bugs.

The interface layer maps `Err` to HTTP through one table in `interface/errors.py`.
Adding a domain error without adding a mapping must fail a test.

### Strategy — `domain/policies.py`

*Justification: the spoiler rule is the single most likely thing to change, and
isolating it makes it exhaustively unit-testable without constructing a feed.*

```python
class SpoilerPolicy(ABC):
    def is_spoiler(self, post: Post, viewer: MemberName,
                   viewer_position: Position | None) -> bool
```

`ChapterFirstSpoilerPolicy` is the only implementation:

```
own post                                    → False
viewer position unknown                     → False
post has no chapter                         → False
post.chapter > viewer.chapter               → True
post.chapter == viewer.chapter
  and both pages present
  and post.page > viewer.page               → True
otherwise                                   → False
```

Chapter dominates because the two members may hold different editions where page
numbers do not correspond, or one may be on audio with no pages at all. Both pages
must be present for the page comparison; inside a single chapter, a false blur is
more irritating than a mild spoiler.

### Mapper — `adapters/notion/mappers.py`

*Justification: Notion property names and shapes are the most fragile knowledge in
the codebase. One class per entity keeps that knowledge in one place, and lets
mapping be tested against recorded fixtures with no HTTP.*

`BookMapper` and `PostMapper`, each with `to_domain(page: dict) -> Entity` and
`to_properties(entity) -> dict`. Property names are module-level constants. Nothing
outside these two modules may reference a Notion property name as a string.

`to_domain` must be forgiving: an unrecognised `Status` becomes `Upcoming`, a
missing number becomes `None`. The owner edits these rows by hand in Notion, and a
hand-edit must not 500 the app.

### Decorator — `application/caching.py`

*Justification: caching is orthogonal to feed assembly. Wrapping keeps
`FeedAssembler` free of cache concerns, and lets every assembler test run without
cache interference.*

`CachingFeedQuery` implements the same interface as the feed query use case and
wraps an instance of it. 20-second TTL, in-memory, keyed by book and filter.
**Any write invalidates the whole cache** — the dataset is tiny and selective
invalidation is not worth the bug surface. Invalidation happens in one place: a
single hook on successful commit, not at each call site.

Twenty seconds is tuned to the refresh model. The frontend refreshes on window
focus, so a member alt-tabbing back repeatedly must not fire a Notion query each
time.

### Composition root — `composition.py`

*Justification: the object graph must be constructible from HTTP handlers, from
tests, and from CLI scripts. FastAPI's `Depends` covers only the first.*

A hand-written `Container` class, not `dependency-injector`. Sixty explicit lines
read better than string-keyed provider wiring, and the wiring is the part a
newcomer most needs to be able to read.

```python
class Container:
    def __init__(self, settings: Settings): ...
    async def startup(self) -> None      # build client, resolve data source ids
    async def shutdown(self) -> None
    def uow_factory(self) -> Callable[[], UnitOfWork]
    def create_post(self) -> CreatePost   # one accessor per use case
```

`main.py` builds one container in the lifespan handler and stores it on
`app.state`. Router dependencies pull use cases from it. Tests build a container
with the in-memory adapters and no HTTP at all.

Use cases receive their collaborators through **constructor injection only**. No
module-level singletons, no service locator, no importing the container from
inside a use case.

## SOLID, concretely

- **Single responsibility** — the split that matters here is one class per reason
  to change: `NotionHttpClient` changes when Notion's transport rules change,
  `PostMapper` when its property names change, `ChapterFirstSpoilerPolicy` when the
  blur rule changes. If two of those would change together, they were split wrong.
- **Open/closed** — a percent-based spoiler rule should be a new `SpoilerPolicy`,
  not an `if` inside the existing one. A SQLite backend should be a new adapter
  package, not a branch in the Notion one.
- **Liskov** — the contract suite in Phase 3 *is* the Liskov check. Every port
  implementation runs the same tests.
- **Interface segregation** — `BookRepository` and `PostRepository` stay separate
  even though one `NotionUnitOfWork` supplies both, so a use case that only reads
  books cannot reach posts.
- **Dependency inversion** — the ports live in `ports/`, next to the domain that
  defines them, not next to the Notion code that implements them. The direction of
  the import is the whole point.

## Configuration

`pydantic-settings`, loaded from `backend/.env`. Required: `NOTION_TOKEN`,
`NOTION_BOOKS_DB_ID`, `NOTION_POSTS_DB_ID`, `MEMBER_NAME`, `MEMBERS`.
`MEMBERS` is the full roster (both names, comma-separated) and must contain
`MEMBER_NAME`; fail at startup if it does not, because an installation that is not
in its own roster will render a broken spine.

Commit `.env.example`. Never commit `.env`. Add it to `.gitignore` in the same
commit that creates it.

## Dependencies

Backend: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic-settings`.
Tests: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`.
Frontend: `react`, `react-dom`. Tests: `vitest`, `@testing-library/react`, `msw`.

Do not add `notion-client` — its support for `2025-09-03` lags, and the adapter is
a thin wrapper over `httpx` with no version ambiguity. Do not add an ORM, a task
queue, Redis, Docker, mypy, or a linter config. Do not add Tailwind or a component
library; the token system above is small and hand-written on purpose.
