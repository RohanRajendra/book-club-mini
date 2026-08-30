# 03 — Testing strategy

## The working loop

Every unit of behaviour is built red → green → refactor.

1. Write one failing test naming the behaviour. Run it. **Confirm it fails for the
   reason you expect** — a test that passes before the code exists is testing
   nothing, and a test that fails on an import error is not yet red.
2. Write the least code that makes it pass.
3. Refactor with the suite green.
4. Commit. One commit per cycle or per small group of cycles.

Each phase file lists its tests in the order they should be written. That order is
the build order. Do not write the implementation first and back-fill tests — the
phase files are structured so that the tests are the design.

## Coverage targets

| Layer | Target | Enforced by |
|---|---|---|
| `domain/` | 100% lines and branches | `--cov-fail-under=100` scoped to the package |
| `application/` | 100% lines and branches | same |
| `ports/` | n/a (ABCs) | excluded |
| `adapters/` | ≥90%, all mapping and error paths | `--cov-fail-under=90` |
| `interface/` | ≥90%, every error mapping | same |
| Frontend hooks and helpers | ≥90% | `vitest --coverage` |
| React components | not tested | — |

100% is demanded on the domain and application layers **only**, because they are
pure and the target is achievable there without contortion. Chasing 100% on HTTP
adapters produces tests that assert a mock was called, which is worse than the
gap. If a domain branch is genuinely unreachable, delete the branch rather than
writing a test that reaches it artificially.

Coverage is a floor, not the goal. A test that asserts nothing meaningful counts
toward coverage and is still a liability.

## Test taxonomy

```
tests/
├── unit/            domain and application. No I/O, no mocks of our own code
├── contract/        one suite, run against every port implementation
├── integration/     Notion adapter against respx. Real HTTP shapes, no network
├── api/             FastAPI routers via httpx ASGI transport + in-memory adapters
└── architecture/    import direction, error-mapping completeness
```

### Unit tests

Domain and application layers. Construct entities directly. **Do not mock domain
objects** — a `Position` is cheap to build and mocking it tests nothing. The only
substitution allowed at this level is passing in an in-memory port implementation,
which is not a mock but a real implementation.

`FeedAssembler` tests get an `InMemoryUnitOfWork` pre-loaded with posts. If a test
needs a mocking library to express itself, the code under test is taking too many
collaborators.

### Contract tests — the important ones

One abstract test class defines the behaviour every port implementation must
exhibit. Both adapters subclass it and supply their own fixture.

```python
class UnitOfWorkContract:
    @pytest.fixture
    def uow(self) -> UnitOfWork: raise NotImplementedError

    async def test_added_post_is_retrievable(self, uow): ...
    async def test_archived_post_is_not_listed(self, uow): ...
    async def test_full_body_round_trips_above_1900_chars(self, uow): ...
    # ...

class TestInMemoryUnitOfWork(UnitOfWorkContract):
    @pytest.fixture
    def uow(self): return InMemoryUnitOfWork()

class TestNotionUnitOfWork(UnitOfWorkContract):
    @pytest.fixture
    def uow(self, respx_mock): return NotionUnitOfWork(...)
```

This is what makes the in-memory adapter trustworthy as a test double, and it is
the Liskov check for the whole port design. A future SQLite adapter is correct when
this suite passes against it — that is the concrete meaning of the swappability
goal.

Where the fake and Notion legitimately differ, mark the test:

```python
@pytest.mark.fake_only(reason="Notion has no transactions; rollback is compensating")
```

Every such marker needs a reason string. Two are expected: true rollback
semantics, and ordering guarantees. A third should prompt a design conversation.

### Integration tests

The Notion adapter against `respx`, never the network. Assert on the **outbound
request** as much as the parsed response — the failure mode this catches is sending
a database ID where a data source ID belongs, and only a request assertion sees it.

Required cases:

- Query hits `/v1/data_sources/{ds}/query`, not `/v1/databases/{db}/query`
- Page creation sends `parent.type == "data_source_id"`
- Every request carries `Notion-Version: 2025-09-03`
- Cursor pagination follows `next_cursor` and stops at the page cap
- 429 triggers retry honouring `Retry-After`
- 4xx other than 429 does not retry
- Rate limiter serialises a burst below the ceiling
- A body over 1900 chars produces a page write **and** a block append
- A failed block append triggers compensation that archives the created page

Fixtures are real recorded Notion response shapes in `tests/fixtures/notion/`,
scrubbed of IDs. Hand-written approximations of Notion payloads are how a suite
goes green against an API that would reject it.

### API tests

Routers through `httpx.ASGITransport` with a container wired to in-memory
adapters. These test HTTP concerns only: status codes, DTO shape, error mapping,
validation. Business assertions belong in unit tests.

### Architecture tests

Cheap, and they enforce the parts of `02-architecture.md` that reviews miss:

- Nothing in `domain/` imports from `application/`, `interface/`, or `adapters/`
- Nothing in `application/` imports from `adapters/` or `interface/`
- No Notion property-name string appears outside `adapters/notion/`
- Every `DomainError` subclass appears in the HTTP error-mapping table
- Every use case returns `Result`

Walk the AST or the import graph. A dozen lines each.

## Frontend testing

Hooks and pure helpers only. No component tests, no snapshots, no E2E.

This constrains the design rather than reducing it: **all state, derivation, and
formatting lives in hooks and pure functions; components are thin and
presentational.** If a component holds logic worth testing, that logic is in the
wrong place. That is the rule the frontend phase is built around.

Tested:

- `useFeed` — loading, error, refresh-on-focus, refresh deduplication
- `useBooks`, `useComposer`, `useReveal`
- `spineScale(totalChapters, observedMaxChapter)` → scale and estimated flag
- `formatPosition`, `formatRelativeTime`, `assignReaderColour`
- The API client's error handling

`vitest` with `renderHook`, and `msw` to mock `/api/*`. Never mock `fetch`
directly — MSW asserts on real request shapes, which is the same reasoning as
respx on the backend.

## Test naming

`test_<subject>_<condition>_<expected outcome>`.

```
test_spoiler_policy_own_post_is_never_hidden
test_position_resolver_uses_latest_progress_post_not_highest_chapter
test_body_splitter_cuts_preview_at_word_boundary
test_delete_post_archives_replies_before_parent
```

The test list should read as the specification. If a name needs a comment to
explain it, rename the test.

## Fixtures

Builders, not fixture soup. `make_post(**overrides)` and `make_book(**overrides)`
in `tests/builders.py`, defaulting every field so a test states only what it cares
about. A test that sets eight fields to assert one is hiding its own point.

## Running

```
pytest                              # everything
pytest tests/unit -q                # the fast loop, used during red-green
pytest --cov=app --cov-report=term-missing
```

Keep `tests/unit` under two seconds. It is the loop the agent runs hundreds of
times, and a slow one quietly kills the discipline.

No CI configuration, no pre-commit hooks, no tox. One `pytest` invocation.
