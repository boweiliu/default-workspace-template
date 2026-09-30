# signup-preview

Live click-through preview of the sign-up plan-selector redesign.

Serves the connector frontend's real built bundle behind an in-memory stub of
its API (`/accounts/api/*`) -- no real backend, no auth, no database. Signing
up or in always succeeds and sets a fake session cookie; nothing persists
across a restart.

## Scenarios

Each PR under review has its own bundle, picked with `?pr=`:

- `?pr=two` -- the 2-card alternative (Limited, Explorer; PR 1449).
- `?pr=three` -- the 3-card alternative (Limited, Explorer, Ally; PR 1450).
- `?pr=main` -- current `main`, unmodified -- the "before" for any PR's comparison.
- `?pr=studio-wordmark` -- the "Studio" wordmark placeholder (PR 1529).
- `1439`, `1440`, `ally`, `both` -- earlier, now-closed PRs, kept so old links still load.

Combine with the waitlist scenarios below, e.g. `/signup?pr=two&waitlist=1`.

- `/signup` -- the waitlist off (dev tiers): the plan cards are selectable.
- `/signup?waitlist=1` -- production's default for a signup with no invite
  code: the cards are greyed out under the "Guest (waitlist)" note.
- `/signup?invite=someone@example.com` -- an invited signup: the cards are
  selectable under the invited-email line.

## Updating after a source change

The bundles in `src/signup_preview/assets/builds/` are snapshots, not
a live link. After changing the connector frontend
(`apps/remote_service_connector/frontend` in the `mngr` external worktree),
rebuild on the PR's branch and recopy it into that PR's bundle, then restart:

```bash
cd .external_worktrees/mngr/apps/remote_service_connector/frontend
pnpm install --frozen-lockfile && pnpm run build
rm -rf /home/user/workspace/system/apps/signup_preview/src/signup_preview/assets/builds/<pr>
mkdir -p /home/user/workspace/system/apps/signup_preview/src/signup_preview/assets/builds/<pr>
cp -r dist/* /home/user/workspace/system/apps/signup_preview/src/signup_preview/assets/builds/<pr>/
supervisorctl restart signup-preview
```

Forgetting the restart is the one recurring mistake here (a prior session hit
it too): the preview keeps serving the old bundle and any fix looks like it
didn't take.
