# signup-preview

Live click-through preview of the sign-up plan-selector redesign.

Serves the connector frontend's real built bundle behind an in-memory stub of
its API (`/accounts/api/*`) -- no real backend, no auth, no database. Signing
up or in always succeeds and sets a fake session cookie; nothing persists
across a restart.

## Scenarios

- `/signup` -- the waitlist off (dev tiers): the plan cards are selectable.
- `/signup?waitlist=1` -- production's default for a signup with no invite
  code: the cards are greyed out under the "Guest (waitlist)" note.
- `/signup?invite=someone@example.com` -- an invited signup: the cards are
  selectable under the invited-email line.

## Updating after a source change

The bundle in `src/signup_preview/assets/accounts_dist/` is a snapshot, not
a live link. After changing the connector frontend
(`apps/remote_service_connector/frontend` in the `mngr` external worktree),
rebuild and recopy it, then restart:

```bash
cd .external_worktrees/mngr/apps/remote_service_connector/frontend
pnpm run build
cp -r dist/* /home/user/workspace/system/apps/signup_preview/src/signup_preview/assets/accounts_dist/
supervisorctl restart signup-preview
```

Forgetting the restart is the one recurring mistake here (a prior session hit
it too): the preview keeps serving the old bundle and any fix looks like it
didn't take.
