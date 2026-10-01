---
name: live-preview-accounts-frontend
description: Build a throwaway, shareable before/after preview app for one change to accounts.imbue.com (the connector accounts frontend, apps/remote_service_connector/frontend in mngr-internal). Builds the frontend from real source at a before and an after git ref, renders each touched page as a plain static HTML page, hosts them as a new single-purpose app named for the change, checks it (every page renders, the before build is byte-identical to prod, hosted before pages look exactly like prod, the after pages show the intended change), then shares only that app with everyone @imbue.com and prints a prod / before / after link table for the PR description. Use whenever a PR touches accounts.imbue.com's frontend and reviewers should click through the change; tear the app down once the PR is done.
metadata:
  crystallized: true
---

# Live before/after preview of an accounts.imbue.com change

One run turns a PR branch into a small app of static pages, e.g.
`studio-wordmark-preview`, reviewers open from a link table in the PR:

| Page | Before (prod) | Before (preview) | After (preview) |
|---|---|---|---|
| Sign in | accounts.imbue.com/login | `<app>/before/login/` | `<app>/after/login/` |

Every page is built from the real source at the two refs -- never a mockup --
so the preview cannot drift from what lands. Nothing is shared until the
skill has checked the hosted pages itself.

This is the accounts.imbue.com member of a family: a preview for another
frontend is a sibling skill (`live-preview-<site>`), not a flag on this one.

## Before you start

- The change is committed on a branch in the mngr-internal clone at
  `.external_worktrees/mngr` (pushed, so `origin/<branch>` exists). Uncommitted
  edits are not previewed -- commit first.
- Workspace sharing is enabled (`data/.secrets/share.env` exists), or the
  share and table steps refuse.
- Pick the preview's name: kebab-case, at most 32 characters, named for the
  change and ending in `-preview` (`studio-wordmark-preview`). It becomes the
  app's name, its URL label, and its share scope. A name another app already
  uses (registered, with a `data/.apps/` folder, or with a program file) is
  refused; a preview this skill made can be re-run under its own name.
- Write one sentence of intent: what the after pages should show, and what
  must not change ("the header wordmark reads 'studio' instead of 'minds';
  nothing else changes"). The review step judges the screenshots against it.

## Run it

Run from the workspace root. In a chat, drive the steps one at a time (each
reads what it needs from `data/.apps/<name>/state.json`) so the user sees
progress; `all` chains them for a headless run.

```bash
S=.agents/skills/live-preview-accounts-frontend/scripts/run.py
uv run $S fetch                                                   # [script]
uv run $S pages  --name <name> --after origin/<branch>            # [script]
uv run $S build  --name <name> --side before                      # [script]
uv run $S build  --name <name> --side after                       # [script]
uv run $S render --name <name>                                    # [script]
uv run $S host   --name <name>                                    # [script]
uv run $S verify --name <name>                                    # [script]
uv run $S review --name <name> --intent "<intent>"                # [ai-script]
uv run $S share  --name <name>                                    # [script]
uv run $S table  --name <name>                                    # [script]

uv run $S all --name <name> --after origin/<branch> --intent "<intent>"
```

1. **fetch** -- fetches `origin` in the mngr clone (with the latchkey gateway
   header), so `origin/main` is current.
2. **pages** -- records the refs (`--before` defaults to `origin/main`) and
   works out which pages the change touches: changed files are traced through
   the TypeScript imports to the page modules `index.ts` mounts. Shared files
   (stylesheet, fonts, `index.ts`, build config) map to every page. Prints the
   pages and why. `--pages /login,/manage` overrides discovery.
3. **build** -- builds one side in a throwaway `git worktree` (`pnpm install
   --frozen-lockfile && pnpm run build`), keeps the untouched `dist/` and a
   provenance record, removes the worktree. The before side is built with
   prod's deploy id, so it comes out byte-identical to prod when in sync.
   `all` builds both sides in parallel (about 25-45 s).
4. **render** -- loads every page from each side's `dist/` in a headless
   browser, all requests answered locally (API calls from
   `assets/api_stubs.json`), and saves the rendered DOM, scripts stripped, as
   `site/<side>/<page>/index.html`. Also writes the index page.
5. **host** -- first run: picks a free port, writes
   `system/supervisord.conf.d/<name_with_underscores>.conf`, starts it, and
   waits until it answers. The program registers the app itself. Re-runs
   confirm it is running.
6. **verify** -- against the app's local port: every page loads on both
   sides; the before build's asset hashes equal prod's; prod's document pages
   equal the before build's; each hosted before page is pixel-identical to a
   screenshot of prod (signed-out pages); before and after differ. Writes
   side-by-side sheets (prod | before | after) to `site/_raw/verify/` and the
   index page. Exits 1 on any failure.
7. **review** -- one Claude Haiku call (via `claude -p`) reads every sheet and
   judges each page against the intent. About $0.05-0.10 and under a minute.
   Exits 1 unless every page passes.
8. **share** -- refuses unless verify and review passed; then adds
   `email_domains = ["imbue.com"]` (`--email-domain` to change) to a
   `[services.<name>]` scope in `data/.secrets/share_grants.toml`, through
   the share gateway's own lock-and-atomic-replace helpers. That app only,
   never the workspace. Re-running is a no-op.
9. **table** -- prints the markdown table for the PR description, plus a link
   to the app's index page.

`all` stops before sharing if verify or review fails, and prints where the
sheets are.

## After the run

- **Look at it yourself before telling anyone.** Open
  `data/.apps/<name>/site/_raw/verify/*.sheet.png` (or the app's index page)
  and read a few. The checks prove the preview matches prod and that something
  changed; your eyes confirm it is the right something.
- Save `system/supervisord.conf.d/<program>.conf` with a commit. The site
  itself lives in `data/` (backed up, not committed).
- Paste the table into the PR description.
- **When the PR merges or closes**, run `teardown --name <name>`: stops and
  removes the program, unregisters the app, drops its share scope, deletes
  `data/.apps/<name>/`. It only touches a preview this skill made, and refuses
  any other app's name. Commit the removed program file. Nothing tears a
  preview down automatically, because its links may still be in an open PR.

To refresh after new commits on the branch, re-run from `fetch`: builds,
render, and checks are redone and swapped in place. The app keeps its port
and URL.

## What a reviewer sees

- `/` -- the index: the table, the check results, the side-by-side sheets,
  and quiet links to the source records under `/_raw/` (both untouched
  bundles, provenance with the exact commits, the API answers used, the
  render log, the check report).
- `/before/<page>/`, `/after/<page>/` -- static snapshots. Links between
  captured pages stay within their side. Buttons and tabs do nothing; each
  page is captured once, in the light theme.
- Signed-out pages look exactly as prod shows them to a signed-out visitor.
  `/manage` and `/downloads` exist only signed in, so they are captured as a
  sample account (`preview@example.com`) and have no prod comparison.

## Gotchas

- **A prod mismatch usually means main moved past the last deploy.** verify
  fails when the before build's asset hashes differ from prod's. Pass the
  deployed commit as `--before <sha>` to compare against what is live. Or,
  when comparing against unreleased main is intended, pass
  `--allow-prod-mismatch` (differences become notes on the index page).
- **A new API call fails the render.** Every request is answered from
  `assets/api_stubs.json`; one with no answer stops the render and names the
  call. Add its signed-out answer (match what prod returns) and, if needed,
  a signed-in one.
- **A page that sends the browser elsewhere fails the render** (e.g. a new
  view that needs a signed-in visitor). Give it the right state in
  `PAGE_CATALOG`.
- **A new route** is discovered from `index.ts` and captured signed out under
  its path as its label. Add it to `PAGE_CATALOG` in
  `scripts/accounts_preview_common.py` to give it a label or a signed-in state.
- **Why the app has no folder under `system/apps/`:** every folder there must
  be a Python package, and a package per preview would churn the shared
  lockfile. The program name is underscored because the workspace's guard
  tests reserve hyphenated program names for apps with a manifest. The
  registered name, URL and share scope keep the hyphenated name.
- `--root` and `--mngr-repo` exist for testing from another checkout. Code
  (the share gateway's grants module, `claude_p.py`, `forward_port.py`'s name
  rules) always loads from the checkout the script runs from.
