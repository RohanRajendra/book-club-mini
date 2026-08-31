# Known issues

Defects found in an audit of the backend on 2026-08-31, ranked by the harm they
can do. Each entry names the failing behaviour, where it lives, and roughly what
fixing it costs.

Cost is code change only:

| | Meaning |
| --- | --- |
| **S** | One or two files, under about forty lines |
| **M** | Three to six files plus new tests |
| **L** | Touches a port or both adapters; needs a live datastore round-trip to verify |

Fixed entries stay on the list with the commit that closed them, so the list
doubles as a record of what has been checked.

---

## Tier 1 — silently wrong, or defeats the core feature

**All four are fixed.** They are kept here with what closed them, because a
list of what has been checked is worth as much as a list of what has not.

### 1. Clearing a field silently failed against Notion — **fixed**

The mappers omitted a property when its value was `None`. A Notion `PATCH`
merges rather than replaces, so the old value survived: removing a page number
returned `200` with the page unchanged, and `Total Chapters` could not be
cleared through the API at all. The in-memory adapter replaces the whole
record, so it *did* clear — and the contract suite had no clearing test, so the
project's central correctness claim certified behaviour production did not have.

Closed by writing every property on every update, with the shape that means
empty (`{"number": null}`, `{"rich_text": []}`), and by adding four clearing
tests to the contract suite. Those tests were written first and failed against
the Notion adapter and passed in-memory, which is the divergence stated above.
Five existing tests asserted the omission as intended behaviour and were
inverted.

Verified against a live workspace, because the stateful stub is only this
project's *model* of Notion and this fix depends on Notion honouring an
explicit null. It does: author, total chapters, page and whole position all
cleared.

### 2. A chapter was never bounded by the book — **fixed**

A book stating 45 chapters accepted a post at chapter 99. Worse than a bad
number: position resolution placed the member at 99, nothing was ahead of them,
and blurring switched off for the whole book.

Closed by enforcing `Book.contains_chapter` on create and edit, refusing to
shorten a book below its posts, and adding sanity ceilings at the HTTP
boundary.

### 3. The body endpoint had no viewer and no spoiler check — **fixed**

`GetPostBody.execute` took only a `PostId`, so the full body of a post blurred
for you was one request away. The documented limitation covers the
1,900-character preview travelling to the browser; it did not cover handing over
the whole 200,000-character body on request.

Closed by giving the use case the viewer and the spoiler policy. A body ahead of
you is withheld with `403` unless the request carries `reveal=true`, which is
the member's *Read anyway* decision travelling to the server. Like the ownership
checks, this prevents an accident rather than an attack — both members are
trusted and either could pass the flag. What it stops is a body arriving that
nobody asked to see.

The check costs one extra query, and only on the path that was already making
two. It is skipped once the post has been revealed, which is the common case for
a long one.

Known wrinkle, deliberately left: the **View as** diagnostic changes the feed's
spoiler flags but not this endpoint, which always uses the installation's own
member. The mismatch is in the permissive direction — a post shown blurred under
*View as* may still return its body — and *View as* is a diagnostic, not a
second identity.

### 4. Blank identifiers returned 500 — **fixed**

The routers built `BookId(...)` and `PostId(...)` straight from user input, and
that constructor *raises* on a whitespace string. `GET /api/books/%20/feed`,
`PATCH /api/books/%20`, `DELETE /api/posts/%20` and `{"book_id": ""}` were all
unhandled crashes: entity guards documented as last-line assertions against a
programming error, reachable from the network.

Closed by translating the exception at the boundary rather than restating the
rule. Path parameters arrive as typed identifiers through a dependency that
answers `422`; identifiers in a request body are stripped and rejected when
empty by the schema, which also tolerates the stray space on a pasted id.

`422` is for an id that could not exist; `404` still means one that simply does
not. Both are pinned.

---

## Tier 2 — wrong output, recoverable

### 5. A 200,000-character post could be previewed as one character — **fixed**

`BodySplitter` took the *last* space in the first 1,900 characters as the cut
point. A body of `"I "` followed by five thousand non-spaces previewed as `I`.
Any space-sparse text hit this — a long URL after a one-word lead-in, base64,
CJK — and newlines were not treated as word boundaries at all.

Closed by making the word boundary a preference rather than a rule. The cut
looks for the last *whitespace*, not the last space, and is only taken when it
leaves at least four fifths of the budget (`MIN_PREVIEW`). A trailing token up
to 380 characters is still dropped whole; anything longer is split mid-word,
because a clean cut is worth a few characters and not a thousand.

Seven mutations, all killed. The one that survived the first pass — dropping
`rstrip()` — showed that no test put a *run* of whitespace at the cut, only a
single space.

### 6. `type=Progress` with a `parent_post_id` bypassed "body required" — **fixed**

`CreatePost` checked the *requested* type, but the effective type was
overwritten to `Reply` further down, after the check. Progress is the one type
exempt from needing a body, so that combination stored an empty reply — over
HTTP, not just in theory. `EditPost` keys off the stored type and never had the
hole, so the two use cases disagreed about one rule.

Closed by deciding the effective type once, before any rule runs: a parent makes
the post a reply whatever was asked for. Nothing downstream reassigns it. The
coercion itself is intended and stays — the parent wins — so the same request
with a body is still accepted as a reply.

Four mutations, all killed.

### 7. Deleted posts remained fully operable — **fixed**

`Post` carried no archived state, and `PostRepository.get` is contractually
required to return archived posts — deliberately, because a soft delete has to
stay recoverable. With nothing to tell the two apart, a deleted post answered
exactly like a live one: editing it returned `200`, deleting it twice returned
`204` twice, and its body was still fetchable.

Closed by making deleted-ness visible rather than by hiding the row. `Post`
gains `is_deleted`, set by the store on read — the in-memory adapter derives it
from its archived set, the Notion adapter from `in_trash` (or the pre-2025-09-03
`archived` spelling). The write side already had that fallback; the read side
did not.

Four use cases read a post by id, so the rule lives once in
`application/post_access.py`. The fourth was not in the original report and
turned up while wiring the other three: **replying to a deleted post** was
accepted, and the reply then never appeared anywhere.

Absent and deleted give the same answer on purpose. A member who deleted a post
does not need the difference explained, and explaining it would leak that the
row is still there.

Nine mutations, all killed. The survivor on the first pass was reading only
`in_trash` and not the legacy `archived` — a spelling the write path handles and
no test read back.

### 8. An in-flight read repopulated the cache with pre-write data — **fixed**

`invalidate()` can only clear what is already in the map. A read still waiting
on Notion has nothing there to clear, and stored its pre-write snapshot the
moment it returned — exactly the staleness the `on_commit` hook exists to
prevent, arriving through the one gap the hook cannot see.

Closed with a generation counter. Every invalidation bumps it; a read carries
the value it started with and stores its result only if that value still holds.
The caller who asked still gets their answer — it was true when they asked —
but it does not become everyone else's answer for the next twenty seconds.

Six mutations, all killed. The survivor on the first pass was stamping the entry
with the time the read *returned* rather than the time it began; the audit read
that as part of the defect, and it is the opposite — a slow read expiring sooner
is the safe way round. It is now a documented decision with a test, rather than
an accident.

This is the suite's first test that actually interleaves two operations. The
audit's own note that there are no concurrency tests is what made the race
invisible: everything else runs to completion between statements, so a write
landing *during* a read was not a state any test could reach.

### 9. Position resolution picks the wrong post of a same-second tie — **S**

`>=` keeps the last post seen, and `list_for_book` is contractually newest-first,
so a tie resolves to the older post. Notion timestamps have second resolution,
so correcting a mistyped chapter within the same second keeps the mistake — the
precise workflow the resolver was written to protect.

### 10. Pagination cap crossed with the delete cascade — **M**

`list_for_book` truncates at 500 posts and `DeletePost` finds replies by
scanning it. Replies past the cap survive their parent, then vanish from the
feed entirely while still consuming the query budget.

---

## Tier 3 — latent, narrow, or needs an out-of-band trigger

| # | Issue | Cost |
| --- | --- | --- |
| 11 | An oversize title or author passes every layer, Notion rejects it, and the member is told "Can't reach Notion right now" — a 502 for a typing mistake. No `max_length` on `BookRequest`. | S |
| 12 | Length limits count code points; Notion counts UTF-16. An emoji-heavy 1,900-character preview is 3,800 units and breaches Notion's cap. | M |
| 13 | `author` is never stripped, only `title` is. A whitespace author is stored, displays blank-but-present, and cannot be removed (see #1). | S |
| 14 | Posts whose book relation is empty are given the fabricated id `BookId("orphan")` — invisible forever, a latent collision, and a hole in the guarantee that identifiers never silently substitute. | S |
| 15 | A member name read from Notion is never checked against the roster and compares by exact string. Roster `Ada` against Notion `ada` is two people, and your own posts get blurred back at you. | S |
| 16 | `?type=Reply` is an accepted filter that always returns an empty feed, with no `reply` count to explain why. | S |
| 17 | A naive `datetime` from any source crashes the whole feed with a `TypeError` during sorting. `created_at=None` is permitted by the entity and does the same. | S |
| 18 | `edited_at` earlier than `created_at` — clock skew, or a duplicated Notion page — makes `was_edited` permanently false. | S |
| 19 | Two concurrent "set currently reading" operations both read before either writes, leaving two current books, never detected or repaired. | M |
| 20 | `EditPost` is an unguarded read-modify-write. Last write wins silently, and a failed second edit's compensation restores state from before the first, undoing a committed change. | L |
| 21 | A reply created between the delete cascade's scan and its archive survives the parent and becomes permanently invisible. | M |
| 22 | A reply inherits its parent's position, so a reply written at chapter 40 under a chapter-2 thought is never blurred. | M |
| 23 | The feed cache is per-process and per-installation. Running more than one worker, or the second member's machine, never invalidates it. | M |
| 24 | Sorting books raises on any status outside the ordering list — a 500 on `GET /api/books` the day a fifth status is added. | S |
| 25 | A use case that writes and then returns `Err` does not roll back; only a raised exception does. No current path does it, but one added guard clause would. | S |

---

## Test-suite weaknesses

Coverage is high — 100% line and branch on `domain/` and `application/` — and
that is exactly how issue #2 survived. Every test was written by reading an `if`
and covering its branches, a procedure that terminates green and can never
surface a rule nobody wrote. The suite is a regression harness for the
implementation, not a specification of the product.

- **No cross-entity invariant is tested anywhere.** Every validation is
  intra-object or single-lookup. Issue #2 was one instance of a missing class.
- **Boundary tests exist only at the low end.** Zero, negative and empty are
  covered diligently; nothing above a limit is ever sent.
- **One non-ASCII value in the whole suite**, and the assertion on the next line
  slices it out of the comparison.
- **No concurrency tests.** The token-bucket burst test is a sequential loop.
- **Every use-case test injects one shared unit of work**, never a real factory,
  so the per-call shape production uses is untested.
- **Vacuous and change-detector assertions**: `assert "body" not in post` on a
  model with no `body` field; `pytest.raises(Exception)` for frozen-ness; a
  constant asserted equal to itself.
- **Four user-facing error strings are duplicated verbatim** across backend and
  frontend with no shared source and no test comparing them. Two more were added
  and are now shared through `application/position_rules.py` and
  `lib/positionRules.js`, which at least name each other.

The convention adopted with issue #2, and worth applying to each fix that
follows: **after adding a guard, delete it and confirm the suite fails.** Eight
mutations were tried against the issue #2 fix; the one that survived exposed an
untested path, which is now covered.

---

## Coverage of this audit

`domain/`, `application/`, `interface/`, the Notion mappers and repositories,
and the whole test suite were swept. A dedicated sweep of the HTTP client, the
compensating unit of work, `rich_text`, config loading, composition and the
shell scripts **did not complete** — the machine slept mid-run, twice. Rate
limiting, retry behaviour, the compensation stack and the setup scripts are
therefore under-represented here, and this list should be expected to grow when
that sweep is finished.
