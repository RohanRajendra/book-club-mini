# Phase 7 — Frontend

**Goal:** the app from `01-ux-spec.md`, with all logic in tested hooks and pure
helpers.

**Depends on:** Phase 6. Build to `01-ux-spec.md` exactly — it is the product
spec and it wins over anything here.

## 7.1 Setup

`npm create vite@latest frontend -- --template react` (JavaScript, not TypeScript —
ten endpoints do not justify the config).

Dependencies: `react`, `react-dom`. Dev: `vitest`, `@testing-library/react`, `msw`,
`jsdom`. Nothing else. No router — the app is one screen. No state manager. No
data-fetching library. No Tailwind or component library; the token system in
`01-ux-spec.md` is small and hand-written on purpose, and a utility framework pulls
a design toward the defaults it ships with.

`vite.config.js`:

```js
server: { proxy: { '/api': 'http://localhost:8000' } }
```

This is why there is no CORS config in the backend.

## 7.2 The rule this phase is built around

**All state, derivation, and formatting lives in hooks and pure functions.
Components are thin and presentational.**

Components are not tested, so any logic inside one is untested by construction. If
a component holds something worth testing, that thing is in the wrong place. This
is a design constraint, not a coverage compromise — treat "I want to test this
component" as a signal to extract a hook.

## 7.3 Pure helpers — write these first

```
src/lib/
├── spineScale.js       spineScale(totalChapters, observedMax) → {max, isEstimated}
├── formatPosition.js   → "Ch 12 · p.204" | "Ch 12" | null
├── formatTime.js       → "3h ago", plus an exact-time formatter
├── readerColour.js     → colour token from roster index
└── api.js              fetch wrapper, error normalisation
```

Tests before implementations:

```
test_spine_scale_uses_total_chapters_when_known
test_spine_scale_infers_with_headroom_when_unknown
test_spine_scale_has_a_minimum_of_ten
test_spine_scale_contains_a_chapter_beyond_a_stated_total
test_format_position_renders_chapter_and_page
test_format_position_renders_chapter_alone
test_format_position_returns_null_with_no_chapter
test_format_time_renders_minutes_hours_and_days
test_reader_colour_is_stable_for_a_given_roster_index
test_api_client_normalises_an_error_body_to_a_message
test_api_client_surfaces_a_network_failure_as_a_readable_message
```

`spineScale` duplicates `ScaleCalculator` from the backend. That is deliberate —
the backend sends the computed scale, and the frontend recomputes it locally for
optimistic updates after posting. The shared test cases keep them honest; if they
ever disagree, delete the frontend copy and render only what the API sends.

## 7.4 Hooks

```
src/hooks/
├── useMe.js         member, roster, colour index
├── useBooks.js      list, add, update, current book selection
├── useFeed.js       feed load, filter, refresh, error state
├── useComposer.js   type, fields, prefill, validation, submit
└── useReveal.js     per-post reveal and expand state
```

```
test_use_feed_loads_on_mount
test_use_feed_exposes_an_error_without_clearing_existing_posts
test_use_feed_refreshes_on_window_focus
test_use_feed_does_not_refresh_on_focus_while_a_request_is_in_flight
test_use_feed_refetches_when_the_book_changes
test_use_feed_refetches_when_the_filter_changes
test_use_composer_prefills_chapter_and_page_from_the_viewer_position
test_use_composer_allows_clearing_a_prefilled_chapter
test_use_composer_requires_a_chapter_for_progress
test_use_composer_allows_an_empty_body_for_progress
test_use_composer_requires_a_body_for_thought_and_question
test_use_composer_keeps_its_contents_when_a_submit_fails
test_use_reveal_reveals_one_post_without_revealing_others
test_use_reveal_state_does_not_persist_across_a_remount
test_use_books_setting_a_book_current_refetches_the_list
```

Two of these encode UX decisions rather than mechanics. Keeping composer contents
on failure is the difference between an annoying app and one that loses your
writing. Not refreshing while a request is in flight is what stops a fast
alt-tab loop from stacking requests.

Use `renderHook` and `msw`. **Never mock `fetch` directly** — MSW asserts on real
request shapes, which is the same reasoning as respx on the backend.

## 7.5 Components

Presentational only. Props in, markup out.

```
src/components/
├── BookBar.jsx        title, dropdown, refresh, view-as
├── BookForm.jsx       add and edit, same form
├── Spine.jsx          track, ticks, tint, quick-progress trigger
├── QuickProgress.jsx  chapter, optional page, submit
├── Composer.jsx       type buttons, fields, character count
├── FilterChips.jsx
├── Feed.jsx
├── PostCard.jsx       metadata, body, actions
├── BlurOverlay.jsx
└── ReplyList.jsx
```

Points where a component will otherwise drift from the spec:

- **Spine.** The tinted region starts at the **viewer's** tick, not the leftmost
  tick. With no total chapters, the right edge is a dotted fade with no end label.
  A member with no progress gets a greyed tick at the far left labelled
  *Hasn't started*.
- **BlurOverlay.** Author, position, and timestamp stay sharp. Only the body
  blurs, with `user-select: none`. The overlay reads `Ahead of you — Chapter 9`.
- **PostCard.** Edit and delete appear only when `is_own`. Read more appears only
  when `has_full_body`. Delete confirms, and says how many replies go with it.
- **Composer.** Character count appears only past 1,700. Escape collapses without
  discarding.
- **ReplyList.** Oldest first, indented behind a hairline in the replier's colour.

## 7.6 Styling

One `src/styles/tokens.css` holding exactly the custom properties from
`01-ux-spec.md`, then component-scoped CSS files importing nothing else. No colour
or font literal appears outside `tokens.css`.

Load Fraunces, Public Sans, and IBM Plex Mono from Google Fonts with
`display=swap`, subset to Latin.

Quality floor, not optional: usable at 380px, visible keyboard focus on every
control, `prefers-reduced-motion` disabling both transitions, and the composer,
reply box, and quick-progress input all submittable by keyboard alone.

## 7.7 Optimistic behaviour

Posting inserts the new post into the feed immediately and reconciles on the
response. On failure, remove it and restore the composer contents.

Nothing else is optimistic. Edit, delete, and book changes wait for the server —
they are rare enough that the latency is invisible, and reconciling an optimistic
delete against a failed cascade is not worth the code.

Refreshing never blanks the feed. Content already on screen stays until new
content replaces it.

## Acceptance checks

- [ ] `npm run dev` plus `uvicorn` gives a working app with no CORS errors
- [ ] `vitest --coverage` reports ≥90% on `src/hooks` and `src/lib`
- [ ] No component test exists, and no component holds derivable state
- [ ] Every action in the `01-ux-spec.md` inventory works end to end
- [ ] A blurred post shows sharp metadata; reveal is per-post and resets on reload
- [ ] Switching books swaps spine, feed, and positions together
- [ ] A book with no total chapters renders a dotted, unlabelled spine edge
- [ ] Ten focus changes in twenty seconds produce at most one Notion query
- [ ] A failed post keeps the composer contents
- [ ] Keyboard-only operation works; focus is always visible
- [ ] No colour or font literal outside `tokens.css`
