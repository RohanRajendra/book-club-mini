# Phase 4 — Notion adapter

**Goal:** the same contract suite from Phase 3, passing against Notion — tested
entirely against `respx`, never the live API.

**Depends on:** Phase 3, and the fixtures captured in Phase 1.6.

## 4.1 `adapters/notion/http.py`

One `NotionHttpClient` holding one `httpx.AsyncClient` for the process lifetime.
Every Notion call in the app goes through it.

Base URL `https://api.notion.com/v1`. Headers on every request:
`Authorization: Bearer <token>`, `Notion-Version: 2025-09-03`,
`Content-Type: application/json`. Timeout 30s.

**Rate limiting.** Token bucket, capacity 3, refill 2.5/second, guarded by an
`asyncio.Lock` so concurrent handlers cannot both drain it. Aim below the ceiling
deliberately: Notion's ~3/sec is an average, bursts trigger the 429s, and this app
has two users and no throughput pressure.

**Retries.** 429 or 5xx: up to 3 attempts. On 429 sleep for `Retry-After` when
present, otherwise exponential backoff from 1s. Any other 4xx raises immediately —
retrying a 400 just delays the error.

**Errors.** `NotionApiError` carrying status, Notion's `code`, and its message.
This is infrastructure, not a `DomainError`; it becomes a 502 in Phase 6. A raw
Notion error body must never reach the browser.

Inject the clock and the sleep function so rate-limit tests do not actually sleep.
A test suite that waits on a real token bucket is a test suite that gets deleted.

Tests:

```
test_every_request_carries_the_notion_version_header
test_every_request_carries_the_bearer_token
test_429_is_retried_after_the_retry_after_delay
test_429_without_retry_after_uses_exponential_backoff
test_retries_give_up_after_three_attempts
test_500_is_retried
test_400_is_not_retried
test_rate_limiter_serialises_a_burst_of_ten_requests
test_notion_error_body_is_wrapped_not_leaked
```

## 4.2 `adapters/notion/ids.py`

```python
async def get_data_source_id(client, database_id) -> str
```

`GET /v1/databases/{id}`, return `data_sources[0].id`, memoise. Log a warning and
take the first if there is more than one — a second data source means the owner
added one in Notion, which this app does not support.

Resolved once at startup by the container, not per request.

```
test_resolves_first_data_source_id
test_result_is_memoised_and_does_not_refetch
test_warns_when_multiple_data_sources_present
test_raises_a_readable_error_when_data_sources_is_empty
```

## 4.3 `adapters/notion/rich_text.py`

`to_rich_text(content)` chunks into objects of ≤2000 characters, ≤100 objects,
raising above that. `from_rich_text(array)` concatenates `plain_text`. Plus
`plain`, `number`, `checkbox`, `select_name` readers for property shapes.

```
test_short_content_becomes_one_rich_text_object
test_content_over_2000_chars_is_chunked
test_chunk_boundaries_lose_no_characters
test_content_over_200000_chars_raises
test_from_rich_text_round_trips_to_rich_text
test_readers_return_none_for_missing_properties
```

The round-trip test is the one that matters — chunking that drops a character at a
boundary is invisible until someone loses a paragraph.

## 4.4 `adapters/notion/mappers.py`

`BookMapper` and `PostMapper`, each with `to_domain(page) -> Entity` and
`to_properties(entity) -> dict`. Property names are module-level constants. **No
Notion property name may appear anywhere else in the codebase** — the architecture
test from Phase 1 enforces it.

`to_domain` must be forgiving. The owner edits these rows by hand in Notion, and a
hand-edit must not 500 the app:

```
test_unknown_status_maps_to_upcoming
test_missing_author_maps_to_none
test_missing_total_chapters_maps_to_none
test_empty_parent_post_id_maps_to_none
test_post_with_no_chapter_maps_to_no_position
test_created_and_edited_times_come_from_the_page_object
test_book_relation_maps_to_book_id
test_to_properties_omits_none_valued_fields
```

Test these against the real fixtures from Phase 1.6, not hand-written payloads.

`to_properties` generates `Name` as `"{member} · Ch {chapter} · {type}"`, or
`"{member} · {type}"` without a chapter. It exists for the owner's eyes inside
Notion and is never parsed back.

## 4.5 `adapters/notion/repositories.py`

**Query shape.** All posts for a book come back in one query — top-level and
replies together:

```json
{
  "filter": {"property": "Book", "relation": {"contains": "<book page id>"}},
  "sorts": [{"timestamp": "created_time", "direction": "descending"}]
}
```

Cursor pagination with `page_size: 100`, capped at 5 pages. Each cursor fetch is a
separate billed request, so a runaway loop is how this app hits the rate limit.
Log a warning at the cap.

Notion excludes archived pages from query results by default. Do not add an
archived filter; do assert that behaviour in a test so a future filter change does
not silently start returning deleted posts.

**Writes.** `POST /v1/pages` with
`parent: {"type": "data_source_id", "data_source_id": ...}`.

Long bodies go into **one** paragraph block, not many. A rich text array holds 100
objects of 2000 characters, so one block covers ~200,000 — and editing a long post
becomes a single `PATCH /v1/blocks/{id}` instead of deleting N blocks and appending
N at 2.5 requests/second.

The four update transitions:

| Was | Becomes | Action |
|---|---|---|
| short | short | patch page properties only |
| short | long | patch properties, **append** a block |
| long | long | patch properties, **update** the existing block |
| long | short | patch properties, **delete** the block |

The contract suite already covers all four. An implementation that handles only
short→short and long→long passes a naive review and fails those tests.

`archive` sends `PATCH /v1/pages/{id}` with `{"in_trash": true}`, falling back to
`{"archived": true}` if rejected. Archival rather than destruction means everything
is recoverable from Notion's trash.

Integration tests assert on the **outbound request** as much as the response:

```
test_query_hits_the_data_source_endpoint_not_the_database_endpoint
test_page_creation_sends_parent_type_data_source_id
test_pagination_follows_next_cursor
test_pagination_stops_at_the_page_cap_and_warns
test_archived_pages_are_absent_from_query_results
test_long_post_creation_sends_a_page_write_and_a_block_append
test_update_long_to_short_sends_a_block_delete
test_update_long_to_long_patches_the_existing_block
```

The first test is the one that catches this API's signature mistake: sending a
database ID where a data source ID belongs. Only a request assertion sees it —
the response mock would happily return success either way.

## 4.6 `adapters/notion/unit_of_work.py`

**Notion has no transactions.** This class implements `rollback()` as compensating
operations, and its docstring must say so in the first line.

As each write succeeds, push its inverse onto a stack:

| Forward | Compensation |
|---|---|
| Create page | Archive page |
| Append block | Delete block |
| Update page properties | Restore the properties captured before the write |
| Archive page | Un-archive page |

`rollback()` replays the stack in reverse, continuing past individual failures and
logging each at ERROR with enough detail to repair by hand. `commit()` clears the
stack — the writes are already durable by then. That is not a bug; document it.

Capturing previous properties before an update costs a read. Only capture for
operations inside a scope that could still fail afterwards; a single-write use case
does not need compensation at all.

```
test_failed_block_append_archives_the_page_that_was_just_created
test_failed_reply_archive_during_delete_leaves_the_parent_intact
test_compensations_run_in_reverse_order
test_a_failing_compensation_is_logged_and_does_not_stop_the_rest
test_commit_clears_the_compensation_stack
test_successful_scope_performs_no_compensating_requests
```

The first test is the requirement that justified this whole pattern: a post whose
preview says "Read more" with no block behind it is worse than a post that failed
to save.

## 4.7 Run the contract suite

Add `TestNotionUnitOfWork(UnitOfWorkContract)` with a `respx`-backed fixture.
**Do not modify the contract.** If a contract test cannot pass, either the adapter
is wrong or the port is — a third `fake_only` marker means stopping to reconsider
the port design, not adding the marker.

The respx fixture needs to behave like a small stateful Notion: pages stored in a
dict, queries filtering over them, archived flags respected. Build it in
`tests/integration/notion_stub.py`. It is a hundred lines and it is what lets the
contract suite run without the network.

## Acceptance checks

- [ ] The Phase 3 contract suite passes against `NotionUnitOfWork`, unmodified
- [ ] Still exactly two `fake_only` markers
- [ ] No test in the suite makes a real network call
- [ ] `app/adapters/notion` is at ≥90% coverage with every error path covered
- [ ] Mapper tests run against the real fixtures from Phase 1.6
- [ ] The architecture test confirms no Notion property name outside this package
- [ ] Swapping `InMemoryUnitOfWork` for `NotionUnitOfWork` in a scratch script
      against the real workspace creates, edits, and deletes a post correctly
