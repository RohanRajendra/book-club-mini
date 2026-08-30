# Phase 6 — HTTP interface

**Goal:** the API surface, the DI container, and a running backend.

**Depends on:** Phase 5. Thin phase by design — if a router grows logic, it belongs
in a use case.

## 6.1 `composition.py`

The container from `02-architecture.md` §Composition root. Hand-written, not
`dependency-injector`.

```python
class Container:
    def __init__(self, settings: Settings)
    async def startup(self) -> None       # build http client, resolve data source ids
    async def shutdown(self) -> None
    def uow_factory(self) -> Callable[[], UnitOfWork]
    def create_post(self) -> CreatePost   # one accessor per use case
    ...
```

Construct the singletons once — HTTP client, resolved data source IDs, spoiler
policy, cache. Build use cases per call; they are cheap and stateless.

```
test_container_builds_every_use_case
test_container_resolves_data_source_ids_once_on_startup
test_container_shutdown_closes_the_http_client
test_a_test_container_can_be_built_with_in_memory_adapters_and_no_http
```

The last test is the container's real job. `Depends` alone would cover HTTP;
tests and scripts need the graph too.

`main.py` builds one container in the lifespan handler, stores it on `app.state`,
and closes it on shutdown. Failing to resolve data source IDs must fail at boot,
not on the first request.

## 6.2 `interface/schemas.py`

Pydantic request and response DTOs, **separate from domain entities**. The domain
must not grow a `model_config` and the API must not break when a domain field is
renamed. Conversion is explicit, in one direction, in one place.

```
PostResponse, ReplyResponse, PositionResponse, SpineResponse,
FeedResponse, BookResponse, CreatePostRequest, EditPostRequest,
BookRequest, BodyResponse, MeResponse
```

`PostResponse` carries `is_spoiler` and `is_own` — both computed server-side, so
the client never sees the blur rule or the ownership rule.

```
test_post_response_never_includes_the_full_body
test_feed_response_includes_a_position_entry_for_every_roster_member
test_error_response_shape_is_a_single_error_string
```

## 6.3 Routes

| Method | Path | Use case |
|---|---|---|
| GET | `/api/health` | — |
| GET | `/api/me` | returns `member`, `members`, reader colour index |
| GET | `/api/books` | `ListBooks` |
| POST | `/api/books` | `AddBook` |
| PATCH | `/api/books/{book_id}` | `UpdateBook` |
| GET | `/api/books/{book_id}/feed?type=&as=` | `CachingFeedQuery` |
| POST | `/api/posts` | `CreatePost` |
| PATCH | `/api/posts/{post_id}` | `EditPost` |
| DELETE | `/api/posts/{post_id}` | `DeletePost` |
| GET | `/api/posts/{post_id}/body` | `GetPostBody` |

There is no session or auth route. Identity comes from `MEMBER_NAME` in this
installation's `.env`.

The `as=` query parameter backs the **View as** control. It changes only which
member's position drives the spoiler flags — it never changes post attribution.
Reject a value outside the roster with 400, and make sure the cache key includes
it.

A router does three things: parse the DTO, call one use case, map the `Result`.
Anything else is misplaced.

## 6.4 `interface/errors.py`

One table from `DomainError.code` to HTTP status and message.

| Error | Status |
|---|---|
| `BookNotFound`, `PostNotFound` | 404 |
| `NotPostOwner` | 403 |
| `CannotReplyToReply`, `ReplyBookMismatch`, `ChapterRequiredForProgress`, `PageRequiresChapter`, `BodyRequired`, `BodyTooLong`, `TitleRequired`, `UnknownMember` | 400 |
| `NotionApiError` | 502 |
| anything unhandled | 500 |

Every response body is `{"error": "<one human sentence>"}`. The 502 message is
*"Can't reach Notion right now. Try refreshing."* — matching the UX copy exactly,
so the frontend can display it verbatim rather than substituting its own.

```
test_every_domain_error_subclass_appears_in_the_mapping   # architecture test
test_notion_api_error_becomes_502_without_leaking_the_body
test_unhandled_exception_becomes_500_without_a_traceback
```

The first is an architecture test, not a unit test. Adding a domain error without
a mapping should fail the build, because the default would otherwise be a silent
500 in production.

## 6.5 API tests

`httpx.ASGITransport` against a container wired with in-memory adapters. HTTP
concerns only — status codes, DTO shape, validation, error mapping. Business
assertions stay in Phase 5.

```
test_health_reports_both_data_source_ids
test_me_returns_the_configured_member_and_roster
test_feed_returns_posts_positions_and_spine
test_feed_with_an_unknown_book_returns_404
test_feed_with_an_unknown_as_member_returns_400
test_create_post_returns_201_with_the_created_post
test_create_progress_without_a_chapter_returns_400_with_a_readable_message
test_edit_another_members_post_returns_403
test_delete_returns_204
test_body_endpoint_returns_the_full_text
test_malformed_json_returns_422_not_500
```

## 6.6 No CORS

The Vite dev proxy in Phase 7 puts both servers on one origin. Do not add
`CORSMiddleware`. If a CORS error appears during Phase 7, the proxy is
misconfigured — fix the proxy.

## 6.7 Logging

Log every outbound Notion request at INFO with method, path, and elapsed time.
This is the only instrumentation worth having: when the app feels slow the question
is always "how many Notion calls did that cost," and this answers it at a glance.
No metrics, no tracing.

Add one test asserting that a feed request produces exactly one outbound Notion
call. That number is the app's core performance property and it should fail loudly
if a future change breaks it.

## Acceptance checks

- [ ] `uvicorn app.main:app --reload` starts and resolves both data source IDs
- [ ] `GET /api/health` returns both IDs
- [ ] A bad `NOTION_TOKEN` fails at startup with a readable message
- [ ] Every route is reachable and returns the documented status codes
- [ ] `app/interface` at ≥90% coverage with every error mapping exercised
- [ ] A feed request against the real workspace costs exactly one Notion call
- [ ] Two feed requests within 20 seconds cost one Notion call
- [ ] Two feed requests with different `as=` values are cached separately
- [ ] No `CORSMiddleware` anywhere in the codebase
