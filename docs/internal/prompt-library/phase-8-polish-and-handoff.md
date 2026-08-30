# Phase 8 — Polish and handoff

**Goal:** two people on two machines are actually using it, and the code says what
it is.

**Depends on:** Phase 7.

## 8.1 `dev.sh` and `setup.sh`

`dev.sh` runs uvicorn and Vite together, trapping SIGINT so one Ctrl-C stops both.
No Docker, no Procfile, no process manager.

`setup.sh` matters more than it looks, because the second installation is the
highest-friction part of this whole design. It should:

1. Check Python ≥3.11 and Node ≥20, and say what to install if not
2. Create the venv, install backend and frontend dependencies
3. Prompt for `NOTION_TOKEN`, `MEMBER_NAME`, and the two database IDs, and write
   `.env`
4. Run `scripts/verify_notion.py` and print the ✓/✗ table
5. Print the one command to start the app

The failure it exists to prevent is her getting a 404 from Notion and having no
idea that the cause is an unconnected integration.

## 8.2 The second-machine walkthrough

Do this for real, on her machine, with her token. It is the acceptance test for
the whole topology decision.

- Clone, run `setup.sh`, start the app
- Confirm her `MEMBER_NAME` appears in the header and her roster shows both names
- She posts progress; you refresh and see her tick move on the spine
- You post ahead of her; she sees it blurred with the right chapter in the overlay
- She replies to a blurred post without revealing it — confirm the reply composer
  does not leak the parent's text
- Both post within a few seconds and confirm neither hits a 429

## 8.3 Full-path exercise

The paths that unit tests miss:

- Post over 1900 characters, edit down to 200, edit back up. Check Notion after
  each: one block, then none, then one
- Delete a post with two replies; confirm all three leave the feed and all three
  are in Notion's trash
- Add a second book, set it current, confirm the first flipped to `Paused`
- Add a book with a title only; confirm the spine renders with a dotted edge and
  calibrates as posts arrive
- Fill in the chapter count later; confirm the spine snaps to the true scale
- Kill the backend mid-session and refresh: the error appears, the feed stays on
  screen, and the app recovers when the backend returns
- Use **View as** to check her blur state, then confirm a post you make is still
  attributed to you

## 8.4 `docs/decisions.md`

One entry per pattern in `02-architecture.md`: what it is, the requirement that
justified it, and what would have to change for it to be removed. If the agent
added a pattern not in that file, it needs an entry too.

This is the file that stops the next person from either ripping out abstractions
that are load-bearing or adding more by pattern-matching.

## 8.5 README

Setup for both machines, then be straight about five things a future reader will
otherwise misjudge.

**There is no authentication.** Each installation declares who it is in `.env` and
the server believes it. The ownership checks on edit and delete prevent accidents,
not attacks. This is fine between two people running on their own machines. It
would not survive being put on the internet, and putting it there is a redesign,
not a deployment.

**Blur is not secrecy.** Blurred post text is sent to the browser and is readable
in devtools. It is a courtesy against accidental spoilers.

**The Notion workspace must stay solo.** Do not invite the second member to Notion.
Adding a member to a free workspace triggers a 1000-block team trial limit, and the
integrations are the only writers.

**Rollback is compensating, not atomic.** `NotionUnitOfWork` undoes failed
multi-step writes by replaying inverse operations. A compensation can itself fail,
and a concurrent reader can observe an intermediate state. Failed compensations are
logged at ERROR with enough detail to repair by hand.

**The rate limit is the real ceiling.** Roughly 3 requests/second per integration.
The app is built around it: one query per feed load, a 20-second cache, no polling.
Any future feature that fetches per-post data in a loop breaks this first.

## 8.6 Known limits

Write these down rather than fixing them:

- A feed caps at 500 posts per book. Past that, older posts stop appearing. The fix
  is date-bounded queries, not a bigger cap
- Editing a post does not update the positions copied onto its replies
- No full-text search. Notion's search API is workspace-wide and filters poorly;
  search in Notion directly
- Positions assume both members use the same chapter numbering. Page numbers may
  differ between editions, which is why the spoiler rule leans on chapter
- Only the first data source of each database is used
- The two installations do not know about each other. There are no notifications
  and no real-time updates; you find out she posted by refreshing

## 8.7 Swapping the database

Note it, do not build it. The work is: implement `BookRepository`,
`PostRepository`, and `UnitOfWork` in a new adapter package, point the container at
it, and run the Phase 3 contract suite. Nothing in `domain/`, `application/`, or
`interface/` changes. On SQLite, `rollback()` becomes a real transaction and the
two `fake_only` markers disappear.

The signals it is time: threading depth, search, or more than about four members.

## Acceptance checks

- [ ] `./setup.sh` takes a clean machine to a running app
- [ ] `./dev.sh` starts both services; one Ctrl-C stops both
- [ ] The second-machine walkthrough passes with the real second member
- [ ] Every path in 8.3 behaves as described
- [ ] Full suite green: `pytest` and `vitest`
- [ ] Coverage gates hold: 100% on domain and application, ≥90% elsewhere
- [ ] `docs/decisions.md` has an entry per pattern
- [ ] README covers setup and all five caveats
- [ ] A fresh clone reaches a running app using only the README
