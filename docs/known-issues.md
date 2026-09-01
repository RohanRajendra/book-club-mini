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

**All six are fixed.** Two of them turned out to be worse than the audit
recorded: #9 is a per-minute tie rather than a per-second one, and #7 had a
fourth reachable path nobody had listed.

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

### 9. Position resolution picked the wrong post of a tie — **fixed**

`>=` kept the last post seen, and `list_for_book` is contractually newest-first,
so a tie resolved to the *older* post: correcting a mistyped chapter kept the
mistake, which is the precise workflow the resolver was written to protect.

The audit called these same-*second* ties and treated them as a narrow race.
A read-only probe of the live workspace says otherwise: **Notion truncates
`created_time` to the minute.** All sixteen pages report `:00.000Z`. Two
progress posts in the same minute tie, so this is the ordinary case. The
workspace already contains one — `Ch 40` and `Ch 4`, both stamped `04:26`, which
is the 40-for-4 mistype the resolver's docstring describes.

Closed by taking the *first* matching post rather than the last, and by making
both stores order a tie newest-first so that "first" means what the contract
says. The in-memory store now sorts on `(created_at, insertion order)`
descending; a plain stable sort resolved a tie to creation order, which is
backwards. The Notion stub had the same flaw and now models what was measured.

Whether the fix reaches production turns entirely on Notion's own tie order, so
that was measured rather than assumed. Under a descending `created_time` sort a
tied pair comes back **newest first**, proved by a causally-ordered pair: a
reply, which cannot predate its parent, is listed before it. The order is also
stable across repeated identical queries.

Six mutations, all killed. One existing test asserted the defect — "last in
input order wins, deterministically" — the third instance of that pattern in
this audit. The test directly below it already said the resolver "must not take
the last one it happens to walk past", but only ever checked it with distinct
timestamps, where the rule makes no difference.

### 10. Pagination cap crossed with the delete cascade — **fixed**

`list_for_book` truncates at 500 posts, and `DeletePost` found replies by
scanning it. A reply past the cap survived its parent — and then vanished,
because feed assembly drops a reply whose parent is missing. Invisible forever,
and still consuming the query budget.

Closed by adding `list_replies(parent_post_id)` to the post repository and
having the cascade ask for what it actually needs. The Notion adapter filters on
the parent id server-side, so the cascade is no longer bounded by the book-wide
cap and costs one query instead of five.

The regression test reproduces the real thing rather than a shrunken version of
it: a parent and its reply, then five hundred newer posts to push the pair off
the end of the last page. Before the fix the cascade reported one post archived
and left the reply behind.

The filter shape was checked against the live workspace, because the stub is
only this project's model of Notion and a wrong shape is a `400` in production
that no stub-backed test can see. Notion accepts `rich_text: {equals: <id>}` on
*Parent Post ID*, returns the one matching reply, and returns zero rows for an
id that does not exist.

Six mutations, all killed.

Still true, and untouched: `list_for_book` itself stops at 500 posts and only
logs a warning. A book that large has a real problem in the feed, which is a
separate issue from the cascade silently missing work.

---

## Reported separately

### A finished book's spine never reached its last chapter — **fixed**

Reported from the UI on 2026-09-01. A book with no chapter count configured got
20% headroom on its scale, so the furthest tick sat at 83% of the track. On a
book marked *Finished* that is simply wrong: headroom exists to leave room for
chapters not yet reached, and there are none. The spine told a member who had
read the whole book that there was more of it.

Closed by making a finished book's furthest posted chapter its length. Every
post counts as evidence, not just progress updates — writing about chapter 45
means someone reached chapter 45. The track is drawn solid and labelled with the
chapter rather than `?`, because on a book that is over this is evidence rather
than a guess.

A stated chapter count still wins; evidence from posts is the fallback, not an
override. Marked finished with nothing posted stays an estimate, since there is
nothing to infer from and a scale of zero is not a spine.

Eight mutations, all killed.

Noticed while fixing it: `frontend/src/lib/spineScale.js` is imported by nothing
but its own test. Its docstring says it exists for an optimistic update after
posting, and that update does not exist. It has been kept in parity with the
backend and is listed in Tier 3 as #26 rather than deleted.

---

## Tier 3 — latent, narrow, or needs an out-of-band trigger

### 27. Hand-edited book text could take the book list down — **fixed**

Found by reading the live workspace while verifying the rest. `Test Book` holds
an empty author, which mapped correctly to absent — but a *whitespace* one did
not, and a whitespace **title** is truthy, so it reached `Book.__post_init__`,
which raises. A `500` on `GET /api/books` and on every feed for that book, from
typing a space into Notion. Same family as #17 and #24: a hand-edit the docs
invite, taking down a read path.

Both fields are now stripped in the mapper, matching what the use cases already
do on write. Three mutations, all killed.

### 19, 21 & 25. Writes that survived what should have undone them — **fixed**

**#25.** `__aexit__` rolled back only when an exception passed through, so a use
case that wrote and then returned `Err` left those writes durable and
unannounced. No current path did it; one added guard clause would have. The port
now rolls back **unless the scope committed**, which is a property of the port
rather than a convention each adapter remembers: `commit` is the base class's
and records the fact, and implementations override `_commit`.

Five integration tests were relying on the old behaviour — writes surviving a
scope that never committed — and needed either a commit or an assertion moved
inside the scope. That is what the defect looked like from the inside.

While pinning it, one thing turned out to be worth stating rather than changing:
an exception *after* a commit does not roll back. Both adapters discard their
undo record at commit, so there is nothing left to undo. The corollary — writes
made after a commit inside the same scope are covered by nothing — is now
written down.

**#21.** A reply created between the cascade's scan and the parent's archive
survived it, then vanished, because feed assembly drops a reply whose parent is
gone. The cascade now looks a second time after archiving the parent. Since a
deleted parent already refuses new replies (#7), that closes the window for
everything except a create already in flight. One extra query on a rare
operation.

**#19.** `_pause_the_current_book` reads every book and then writes, so two
concurrent "set currently reading" calls both survive. The app offers no way to
*express* two current books — the spine and the default book each assume one —
so the state was unreachable by intent and unrepairable once reached.
`ListBooks` now detects it and demotes the extras to Paused.

The repair **writes** rather than only adjusting what is displayed. Notion is the
source of truth and the owner reads it directly, so an app quietly showing one
current book while the workspace held two would be the worse failure. Which book
stays is arbitrary — nothing recorded says which was set most recently — so it
is the one the member already sees first; re-picking is one click.

Ten mutations, all killed. Two survived the first pass. One was equivalent for
both current adapters and still worth pinning, since it breaks the port's
contract for any future backend whose rollback is not a no-op after commit. The
other was real: the repair firing on a *healthy* list, which commits, which
fires the `on_commit` hooks, which invalidates the feed cache — on every book
list, which is most page loads.

### 14, 15 & 16. Identifiers invented, folded, and offered in error — **fixed**

**#14.** A post whose Book relation is empty was given the fabricated id
`BookId("orphan")`. That names no book, breaks the guarantee that an identifier
never silently stands in for another, and left the row invisible anyway, since
the feed queries by that relation. The mapper now returns `None` for a row it
cannot represent and the repositories log and skip it. The row was already
invisible; what changes is that the owner can find out why.

**#15.** `MemberName` compared by exact string, so a roster of `Ada` against a
Notion value of `ada` was two people. The concrete harm: the spoiler rule asks
whether the author is the viewer, the comparison said no, and **your own posts
came back blurred at you** — with your position attributed to nobody. Comparison
now folds case while `value` keeps the spelling it was given, so display is
untouched. The same fold applies to *View as*, whose roster check compared raw
strings.

**#16.** `?type=Reply` was accepted and could only ever return an empty feed:
the filter runs over top-level posts after nesting, because filtering in the
query would strip replies off their parents. The offered filters are now their
own enum, answering `422` for `Reply`, and a test pins that enum to the set the
feed actually counts so the two cannot drift.

Eight mutations, all killed. The survivor on the first pass was the repository's
skip: `list_for_book` can never see an unrepresentable row, since it filters on
the very relation that is missing, but `list_replies` filters on the parent and
can — where a `None` in the list is an `AttributeError` inside the delete
cascade.

One more test asserted the defect and was removed rather than inverted:
`test_a_row_with_no_book_relation_maps_to_an_orphan_book_id`.

### 17, 18 & 24. One bad row could take a whole read path down — **fixed**

Three separate defects, one shape: a value that should make one row look odd
instead broke everything that read it.

**#17.** `sorted` raises on the first pair it cannot compare, so a post with no
`created_at`, or one naive datetime among aware ones, was a `500` for the entire
book rather than one misplaced post. Fixed at both ends: `created_order` is a
total key that reads a naive value as UTC and sorts an undated post oldest, and
the mapper no longer emits a naive or unparseable timestamp at all. Sorting is
the one place a single bad row is fatal, so it is worth guarding twice.

**#18.** An `edited_at` before `created_at` — clock skew, or a page duplicated
inside Notion — silently failed a comparison. It now reads as unedited by an
explicit rule rather than by a negative number happening to lose.

**#24.** Sorting books raised on a status outside the ordering. A missing status
now sorts last, and a completeness test asserts the ordering covers every enum
member — so adding a fifth is a failing test rather than a `500` on
`GET /api/books`.

Twelve mutations, all killed. The survivor on the first pass was a test that
patched the *lookup table* rather than the ordering, so both the old and new
implementations passed it — a test that could not tell the fix from the defect.

**New, found while fixing #18.** The `was_edited` threshold is 60 seconds, and
Notion truncates both timestamps to the minute (see #9), so the only gaps that
exist are 0, 60, 120… A threshold of `> 60` therefore hid **every edit made in
the minute after posting**. The threshold exists for one reason: a long post is
written as a page create then a block append, and the append moves
`last_edited_time` by itself. A short post has no second write, so it needs no
threshold at all — and short posts are the common case. The rule now depends on
`has_full_body`, which is exactly the condition the second write depends on.

### 11 & 13. A book's title and author had no limit and no cleaning — **fixed**

An oversize title or author passed every layer and Notion refused it, which the
member read as "Can't reach Notion right now" — a `502` for a typing mistake,
naming no field. And `author` was never stripped, only `title` was, so a
whitespace author was stored: blank-but-present, and until issue #1 was fixed,
impossible to remove.

Both are one code path, so both are closed together. `TextTooLong` names the
field and both numbers. A title or author is stripped, and whitespace-only is
stored as absent — blank and absent should not be two different states. The
limit counts UTF-16 units, for the reason in #12 below.

The browser form now caps both inputs at 2000 as well. HTML `maxlength` counts
UTF-16 code units, which is the same quantity Notion counts, so the two rules
agree exactly — including for emoji — and the paste is stopped rather than
round-tripped into an error.

Ten mutations, all killed. Two coverage gaps surfaced while checking and both
were real: an unreachable early return in the clip helper, now removed, and the
entity's own cap guard, which the use case shields from every test that goes
through it.

### 12. Every length limit measured the wrong quantity — **fixed**

Notion's 2000-character property cap counts **UTF-16 code units**, not code
points. Confirmed against the live API, which rejects 1001 astral emoji with
`content.length should be ≤ 2000, instead was 2002` — and creates nothing, so
the check cost no cleanup. Python's `len` counts code points, so an emoji-heavy
1,900-character preview is 3,800 units and the write fails as a `502` the member
reads as "Can't reach Notion right now".

Four places measured it: the `Post` preview guard, the body ceiling, the
preview cut, and the rich-text chunker. All now use `domain/text.py`, which also
provides a clip that cuts **between code points** — slicing by unit index
directly would leave half a surrogate pair, which no store accepts and no reader
renders.

Fixing the chunker exposed a second defect underneath. An object closes one unit
short whenever the next character is astral and one unit of budget remains, and
a body can be built where that happens at *every* boundary. At a ceiling of
100 × 2000 such a body is inside the limit and still needs 101 objects, which
Notion rejects. The ceiling is now what 100 objects can be *relied* on to hold —
199,900 — and the body limit moved with it. A test pins the two constants equal,
because the domain cannot import the adapter and nothing else keeps them so.

Verified end to end against the live workspace, since chunking is exactly the
kind of thing a stub agrees with and a real store does not: a body mixing
astral emoji, a flag pair and a family sequence, split into four objects, round
tripped byte-identical. The probe page was archived and the workspace confirmed
back at sixteen posts.

Eleven mutations, all killed. The survivor on the first pass was the word-
boundary floor, which no emoji test reached.


Everything in this tier is now fixed except three items kept deliberately, and
one awaiting a decision. Each of the three has tests pinning the current
behaviour, so a future change to any of them is a choice rather than an
accident.

---

## Kept deliberately

### 20. Concurrent edits are unguarded — **kept, pinned**

`EditPost` reads a post, builds the new version, and writes it. Two overlapping
edits both read the same original and the second write wins, silently.

Detecting it needs a conditional write — "update only if the row still looks the
way I read it" — and Notion has no such operation. The nearest approximation is
re-reading `last_edited_time` before writing, which narrows the window without
closing it, costs a request on every edit, and cannot work anyway: Notion
truncates that timestamp to the minute (#9), so it cannot distinguish two edits
within the same minute, which is exactly when this happens.

**The audit's second claim here was wrong.** It said a failed second edit's
compensation restores state from *before the first*, undoing a committed change.
It does not. `CompensationStack.clear()` empties the captured-properties set
along with the stack, `__aenter__` calls it, and every use-case invocation gets a
fresh unit of work from the factory — so the second edit captures the state the
first one committed. Checked by running it: a failed second edit leaves the
*first* edit's text in place. There is now a test pinning that, because
compensation reaching back across a commit would silently destroy work, and the
audit shows how easy it is to believe it already does.

### 22. A reply's position is its parent's — **kept, pinned**

A reply written at chapter 40 under a chapter-2 thought carries chapter 2 and is
never blurred. The spoiler machinery is not at fault — replies are flagged
independently, and a test pins that — only the position handed to it is
inherited.

Changing it means deciding where a reply's position comes from: the replier's
own progress, which needs a lookup on a path that has none today, or a chapter
field on the reply box, which is new UI on what is currently one text box. Kept
because a thread reads as one conversation, and a thread that half-blurs is
harder to follow than one that does not blur at all.

### 23. The feed cache is per-process — **kept, pinned**

Invalidation reaches one instance. A second worker, or the other member's
machine running its own copy against the same workspace, keeps serving its own
twenty-second-old view after a write.

Fixing it properly means shared state — a cache both processes can reach, or a
signal between them — and neither belongs in an app two people run for
themselves. The failure is bounded: it self-heals in twenty seconds, and a test
pins that bound. Written down because "I posted and they cannot see it" is the
first thing that looks like data loss and is not.

---

## Awaiting a decision

| # | Issue | Cost |
| --- | --- | --- |
| 26 | `frontend/src/lib/spineScale.js` is imported by nothing but its own test. It duplicates the backend calculation for an optimistic update that does not exist, so its tests assert parity with something no member ever sees. Kept in parity with the backend for now; deleting it is the owner's call. | S |

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
  covered diligently; nothing above a limit is ever sent. *Partly addressed:*
  the issue #5 fix pins the preview threshold from both sides, at exactly the
  floor and one character below it.
- **One non-ASCII value in the whole suite**, and the assertion on the next line
  slices it out of the comparison.
- **No concurrency tests.** The token-bucket burst test is a sequential loop.
  *Addressed for three cases:* issue #8 adds the first test that actually
  interleaves two operations, #21 injects a write in the middle of the delete
  cascade, and #20 and #23 pin what happens when two writers or two processes
  overlap. That absence was the reason the race existed —
  everything else runs to completion between statements, so a write landing
  *during* a read was not a state any test could reach.
- **Every use-case test injects one shared unit of work**, never a real factory,
  so the per-call shape production uses is untested.
- **Vacuous and change-detector assertions**: `assert "body" not in post` on a
  model with no `body` field; `pytest.raises(Exception)` for frozen-ness; a
  constant asserted equal to itself.
- **Four user-facing error strings are duplicated verbatim** across backend and
  frontend with no shared source and no test comparing them. Two more were added
  and are now shared through `application/position_rules.py` and
  `lib/positionRules.js`, which at least name each other.

The convention adopted with issue #2, and applied to every fix since: **after
adding a guard, delete it and confirm the suite fails.** 115 mutations across
every fix, all killed. Nine survived a first pass, and each one named a real
hole rather than a cosmetic one:

| Fix | Survivor | What it exposed |
| --- | --- | --- |
| #2 | `_tightens` always true | Clearing a book's total was untested |
| #5 | `rstrip()` deleted | Every boundary test used a single space, never a run |
| #7 | Only `in_trash` read | The legacy spelling was written but never read back |
| #8 | Entry stamped on return | An undocumented decision, and the opposite of a defect |
| #10 | Repository stopped skipping | `list_for_book` cannot see the case; `list_replies` can |
| #12 | Word-boundary floor | No emoji test reached the cut decision |
| #24 | Lookup table patched | A test that passed against the fix *and* the defect |
| #19 | Repair on a healthy list | A read that commits invalidates the cache on every page load |
| #25 | `commit` not recording | Equivalent for both adapters, breaks the port for a third |

The habit that keeps paying: a test written by reading the implementation
terminates green. Five tests in this audit asserted the defect as intended
behaviour and had to be inverted — five in the Notion mappers for issue #1, and
one in the resolver for issue #9, whose neighbour already stated the correct
rule but only checked it where the rule made no difference.

---

## Coverage of this audit

`domain/`, `application/`, `interface/`, the Notion mappers and repositories,
and the whole test suite were swept. A dedicated sweep of the HTTP client, the
compensating unit of work, `rich_text`, config loading, composition and the
shell scripts **did not complete** — the machine slept mid-run, twice. Rate
limiting, retry behaviour, the compensation stack and the setup scripts are
therefore under-represented here, and this list should be expected to grow when
that sweep is finished.
