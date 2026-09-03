# Deployment

The app can run two ways. Both are supported; they differ in one thing only —
where identity comes from.

| | `AUTH_MODE=open` | `AUTH_MODE=passphrase` |
| --- | --- | --- |
| Who you are | `MEMBER_NAME` in the environment | a signed cookie, per browser |
| Sign-in | none | one shared passphrase, then your name |
| Suits | `./dev.sh` on your own machine | one deployment both members reach |

`open` is the default and is what the local workflow has always been. Nothing in
this document is needed to run the app that way.

---

## What a shared deployment looks like

```
https://<project>.vercel.app
  ├─ /            → the Vite build, served from the CDN
  └─ /api/*       → FastAPI, as a Python serverless function
                    the Notion token lives only in the platform's environment
```

One URL. A member opens it, enters the passphrase and their name once, and
stays signed in on that device for 90 days. Nothing is installed and no token
reaches their machine.

Push to `main` → GitHub Actions runs both test suites and the coverage gates →
green deploys, red never ships. Vercel's own git deploys are switched off in
`vercel.json` so this workflow is the only route to production.

---

## Setting it up

Steps 1 and 3 need an account, so they are yours to do.

### 1. Generate the secrets

```bash
cd backend && .venv/bin/python scripts/make_secrets.py
```

It prints a passphrase to share with the other member, and two values to
configure. The passphrase is generated rather than chosen: one someone invents
is the weakest part of the whole design.

### 2. Collect the data source IDs

```bash
cd backend && .venv/bin/python scripts/verify_notion.py
```

The last lines print `NOTION_BOOKS_DATA_SOURCE_ID` and
`NOTION_POSTS_DATA_SOURCE_ID`. They are optional — the app resolves them at
startup if absent — but resolving costs two Notion round trips on *every* cold
start, which on a serverless host is most requests.

### 3. Create the Vercel project

Import the repository. Vercel reads `vercel.json`, so there is nothing to
configure in the dashboard beyond the environment.

Set these for **Production** and **Preview**:

| Variable | Value |
| --- | --- |
| `NOTION_TOKEN` | from `backend/.env` |
| `NOTION_BOOKS_DB_ID` | from `backend/.env` |
| `NOTION_POSTS_DB_ID` | from `backend/.env` |
| `NOTION_BOOKS_DATA_SOURCE_ID` | from step 2 |
| `NOTION_POSTS_DATA_SOURCE_ID` | from step 2 |
| `MEMBERS` | `Rohan,Shreya` — same order as locally, colours come from it |
| `AUTH_MODE` | `passphrase` |
| `SESSION_SECRET` | from step 1 |
| `SITE_PASSPHRASE_HASH` | from step 1 |

**Do not set `MEMBER_NAME`.** It means nothing under `passphrase`, and the app
refuses to treat it as an identity — but leaving it out removes the question.

Then add three repository secrets in GitHub, for the deploy job:
`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`. The last two are in
`.vercel/project.json` after running `vercel link`.

### 4. Check the routing

One request settles the only thing local testing cannot:

```bash
curl https://<project>.vercel.app/api/health
```

`{"status":"ok"}` means the rewrite in `vercel.json` preserves the request path
and every other route will work. A `404` means it does not, and the fix is to
mount the router at `/` and set `root_path="/api"` in `create_app`.

---

## Operating it

**Rotating the passphrase.** Run `make_secrets.py` again and replace both
`SESSION_SECRET` and `SITE_PASSPHRASE_HASH`. Changing the secret signs everyone
out, which is also how a session is revoked if a device is lost.

**Rolling back.** Promote the previous deployment in Vercel. Nothing in Notion
changes — the app holds no state of its own.

**Adding or removing a member.** Edit `MEMBERS`. Someone removed from it is
signed out on their next request, because the roster is checked every time and
not just at sign-in. Order matters: reader colours come from it.

---

## What this does not protect against

Stated plainly, because the app's threat model has not changed as much as
adding a login might suggest.

- **A shared passphrase means either member can pick either name.** So could
  either of them before, by editing a configuration file. Ownership checks
  prevent accidents, not attacks. Upgrading to one passphrase each is a small,
  contained change if that stops being true.
- **Blurring is still presentational.** A post's 1,900-character preview reaches
  the browser and is readable in developer tools. The *full* body of a post
  ahead of you is withheld by the server, but the preview is not. Both members
  are authorised, so this guards against an accidental glance, not a determined
  reader.
- **The Notion token now lives with the platform.** A new party in the trust
  chain, holding a token with full read and write access to everything shared
  with the integration.
- **No IP allowlist.** Home and mobile addresses rotate, so it would lock a
  member out regularly while stopping nobody who has the passphrase. Available
  as an extra later; not as the control.
- **Login throttling is weak by construction.** A fixed delay plus the ~90ms
  PBKDF2 verification, and no counter that survives a process restart — which
  on a serverless host is whenever the platform likes. The passphrase's entropy
  is what defends it, which is why it is generated.
- **The feed cache is per-process** (`docs/known-issues.md` #23), and serverless
  makes that worse rather than better: most requests start a fresh process, so
  the cache rarely hits. Correctness is unaffected — it is an optimisation — and
  two readers will not approach Notion's rate limit.
