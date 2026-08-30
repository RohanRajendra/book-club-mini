# 01 — End-user specification

This is the product. Build to it exactly. Where a phase file and this file
disagree, this file wins.

## Topology

Each member runs their own copy: `./dev.sh` starts a FastAPI backend on `:8000`
and a Vite dev server on `:5173`. Both installations point at the same two Notion
databases through separate integration tokens.

There is no login. `MEMBER_NAME` in `.env` declares who this installation belongs
to. Opening the app puts you straight into the feed.

A **View as** control in the header lets you re-render the page as the other
member. It exists so you can verify blurring works from her side without editing
`.env`. It does not change who your posts are attributed to — a post is always
written as `MEMBER_NAME`. Label it plainly and keep it visually quiet; it is a
diagnostic, not a feature.

## The screen

One route, one screen. Top to bottom:

### 1. Book bar

- Current book title in the display face; author beneath it in muted text.
- A dropdown listing all books grouped by status, in the order *Currently
  reading*, *Upcoming*, *Paused*, *Finished*. Selecting one switches the entire
  screen to that book.
- **＋ Add book** as the last item in the dropdown.
- **Edit book** on the current book, opening the same form as Add.
- A refresh control showing a quiet "updating" state while a request is in flight.
- Your name on the right, with the **View as** control.

### 2. The spine

A horizontal track spanning the content width, representing chapter 1 at the left
to the book's end at the right. One tick per member in their assigned colour,
positioned by chapter, labelled `Ch 12 · p.204` in the mono face, with
`2 days ago` beneath.

Everything to the right of **your own** tick is tinted with the same wash used
behind blurred posts, so the spine explains the blur rule without copy.

**Scale calibration**, since a book may have no chapter count:

- Total chapters known → true scale, last chapter labelled at the right edge.
- Unknown → scale runs from 1 to `max(highest chapter observed in any post, any
  member position)` plus 20% headroom, minimum 10. The right edge is a dotted fade
  with no end label, so it reads as unknown rather than as a claim.
- Filling in the chapter count later snaps the spine to the true scale.

**States.** A member with no progress post shows a greyed tick at the far left
labelled *Hasn't started*. A book with no posts at all shows an empty track with
the prompt *Post where you are to start the spine.*

**Interaction.** Clicking your own tick opens a compact inline **quick progress**
input: chapter, optional page, post. This is the most-used action in the app and
must not require opening the composer.

### 3. New post

A **New post** button above the feed. Clicking it expands an inline composer card
at the top of the feed — not a modal, so the feed stays visible. Escape or
**Cancel** collapses it. Contents survive collapse within the session.

Three type buttons: **Progress · Thought · Question**.

| Type | Chapter | Page | Body |
|---|---|---|---|
| Progress | Required | Optional | Optional — a bare position is a valid post |
| Thought | Optional, **pre-filled** from your position, editable | Optional, pre-filled, editable | Required |
| Question | Same as Thought | Same as Thought | Required |

Pre-filled values are editable and clearable. A thought with the chapter cleared
can never be blurred for anyone — that is the member's choice and the app does not
warn about it.

A character count appears only past 1,700, reading
`1,743 — longer posts are collapsed in the feed`. Nothing is ever truncated or
lost.

A post fails only on validation or a Notion error. On failure the composer keeps
its contents and shows what went wrong.

### 4. Filter chips

*All · Progress · Thoughts · Questions*, each with a count. Filtering applies to
top-level posts; replies stay attached to whatever survives the filter.

### 5. Feed

Newest first. Each card:

- Member initial in their colour, member name
- Position marker in mono (`Ch 12 · p.204`, or `Ch 12`, or nothing)
- Relative timestamp (`3h ago`), exact time on hover
- `edited` marker when `last_edited_time` differs meaningfully from `created_time`
- Body, or preview plus **Read more** when the post is long
- **Reply**
- **Edit** and **Delete** on your own posts only

**Replies** nest one level, indented behind a hairline rule in the replier's
colour, ordered oldest-first — a conversation reads downward inside a feed that
reads upward. The reply box opens inline beneath the post.

**Read more** fetches the full body on click and expands in place. It never
appears on a post that is not actually truncated.

**Blurred posts** show author, position, and timestamp perfectly sharp. The body
is blurred and unselectable under a centred overlay reading
`Ahead of you — Chapter 9` with a **Read anyway** control. Revealing affects one
post and resets on reload. Replies under a blurred parent are evaluated
independently and revealed independently.

Metadata stays sharp on purpose. Knowing that she said *something* at chapter 9
is not a spoiler, and hiding the card entirely would hide that the club is active.

**Edit** turns the card into the composer form in place, pre-loaded with the full
body — fetching it first if the post is long. **Delete** asks for confirmation and
says how many replies will go with it.

## Complete action inventory

| Action | Entry point |
|---|---|
| Add a book | Book dropdown → ＋ Add book |
| Edit title, author, chapter count, status | Book bar → Edit book |
| Switch which book is current | Book dropdown, or the book form's status field |
| Browse a past or upcoming book | Book dropdown |
| Post progress, full | New post → Progress |
| Post progress, quick | Click your spine tick |
| Post a thought or a question | New post |
| Reply to a post | Post card → Reply |
| Edit your own post | Post card → Edit |
| Delete your own post | Post card → Delete |
| Expand a long post | Read more |
| Reveal a blurred post | Read anyway |
| Filter by type | Chips |
| Refresh | Header control, or return focus to the tab |
| Check the other member's view | View as |

## Rules with visible consequences

**Only one book is `Currently Reading`.** Setting a book current moves any other
current book to `Paused`, not `Finished` — the app cannot tell whether you
finished a book or set it aside, and guessing writes a false claim into Notion.

**Position is your most recent progress post, not your highest chapter.** A member
who mistypes chapter 40 for chapter 4 fixes it by posting again. Highest-wins
would strand them.

**No position means nothing is blurred for you.** Blurring the whole feed for
someone who has not posted progress makes the app look broken. The empty spine
prompts them instead.

**Deleting a post deletes its replies.** Notion does not cascade; the app archives
them explicitly. Everything is recoverable from Notion's trash.

**Editing a post does not change its replies' copied positions.** A reply's
position is a snapshot of where the conversation started.

## Refresh model

The feed reloads on window focus and on the manual control. No polling. The
backend's 20-second cache absorbs rapid focus events, so alt-tabbing repeatedly
does not translate into Notion requests.

Refreshing never blanks the feed. Content already on screen stays until the new
content replaces it.

## Empty and error copy

Say what happened and what to do. No apologies, no vagueness.

| Situation | Copy |
|---|---|
| No books | No books yet. Add the one you're reading. |
| No posts | Nothing here yet. Post where you are, or what you're thinking. |
| No progress posted | Post a progress update to start hiding spoilers. |
| Filter has no matches | No questions yet. |
| Notion unreachable | Can't reach Notion right now. Try refreshing. |
| Post failed | Couldn't save that. Your text is still here — try again. |
| Book title empty | A book needs a title. |
| Progress without chapter | Progress needs a chapter number. |

Keep the last-loaded feed on screen behind any error.

## Visual direction

The design axis is otherwise open, so build to this rather than substituting a
generic direction. Derive every colour and type decision from these tokens.

**Concept.** A shared reading ledger — two people keeping margin notes in the same
book at different depths. The design's job is to make "where each of us is"
readable at a glance, and to make a blurred post feel like a closed page rather
than an error.

```css
--field:    #E7E9E4;   /* page ground, cool sage-grey */
--surface:  #F2F3EF;   /* raised cards */
--ink:      #191C18;   /* primary text */
--muted:    #6A7168;   /* metadata */
--rule:     #C2C7BC;   /* hairlines, spine track, blur wash */
--reader-a: #2C5F72;   /* deep petrol */
--reader-b: #7D2E46;   /* deep plum */
```

Reader colours are assigned by index into the member roster so they stay stable.
They are the app's primary wayfinding: name, initial, spine tick, and reply indent
rule all share one hue, so scanning for "what did she say" needs no reading.

**Type.** Display: **Fraunces**, `wght 600`, `WONK 1`, high optical size — book
titles and the club name only, used with restraint. Body: **Public Sans**, 400/600.
Utility: **IBM Plex Mono**, 500, letter-spaced — chapter and page markers,
timestamps, counts. Positions set in mono read as citations, which is what they
are.

**Restraint.** The spine is the single bold element. Everything else stays quiet:
hairline rules, generous line height, 1px borders, no shadows, no gradients, no
icon set. Motion is limited to the blur reveal and the composer expand, both
150ms, both disabled under `prefers-reduced-motion`.

**Quality floor.** Usable down to 380px wide. Visible keyboard focus on every
control. The composer, reply box, and quick-progress input are all reachable and
submittable by keyboard alone.
