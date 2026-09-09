# chat-hub-alt

Standalone home of **chat-hub-alt** — a stripped-down, hackable fork of a
Claude-chat interface (transcript, step/progress timeline, composer, model
picker), plus a small companion backend for switching which chat a tab shows
from outside the browser.

It was forked out of a larger "Minds" agent workspace project to be a
lightweight surface to iterate on chat UI/UX ideas without the weight of the
full workspace shell (no tabbed dockview, no terminal view, no
projects/plugin system — just the chat).

## What's here

- **`frontend/`** — the chat UI (TypeScript + [Mithril](https://mithril.js.org/) + Vite +
  Tailwind). Renders the message transcript (including a client-side
  reconstruction of an agent's step/progress timeline), a composer with file
  attachments, a model/effort picker, and a sidebar to switch between chats.
  Ships **no chat backend of its own** — see "External dependencies" below.
- **`control-backend/`** — `chat-hub-control`, a small dependency-light Flask
  server with one job: let another process on this machine tell every open
  chat-hub-alt tab which chat to show (`POST /select-agent`). Fully
  self-contained, no external dependencies beyond Flask.

## Running it

```
cd frontend && npm install && npm run dev
```

Opens on `http://127.0.0.1:8080/`. In another terminal, if you want the
control channel too:

```
cd control-backend && pip install -e . && chat-hub-control
```

## External dependencies

This repo has no build-time or install-time dependency on the project it was
forked from — it clones and runs on its own. But two things it talks to at
*runtime* are external services, documented as APIs/protocols rather than
vendored code, so you can supply your own compatible implementation (or none
at all — both degrade gracefully):

- **The chat backend.** This app doesn't manage agent processes or talk to an
  LLM itself — it expects a backend implementing the same contract as
  `system_interface` from the forked-from project: `GET /api/agents`,
  `GET /api/agents/:id/events` (+ SSE `/stream`), `POST /api/agents/:id/message`,
  `GET /api/agents/:id/model-options`, a `WS /api/ws` broadcast channel, and a
  handful of neighboring routes (see `frontend/src/models/Response.ts` and
  `AgentManager.ts` for the exact calls). Point it at yours via the
  `CHAT_BACKEND_URL` env var (defaults to `http://localhost:8000`):

  ```
  CHAT_BACKEND_URL=http://localhost:8000 npm run dev
  ```

  Without one, the UI boots fine but every chat action fails — there's
  nothing on the other end.

- **An embedding host shell (optional).** `frontend/src/embed-contract.ts` is
  a small, self-contained reimplementation of a postMessage protocol for
  running this app inside a trusted parent frame: the app can ask a host to
  open its own permission-request review UI (`OPEN_REQUEST_MODAL`), and a
  host can push back permission-request verdicts
  (`PERMISSION_RESOLUTIONS`). It's genuinely optional — opened directly in a
  browser tab (the common case), sends just have no listener and nothing
  ever arrives. If you want to embed this app inside your own shell, build
  the other side of that contract against `embed-contract.ts`'s documented
  message shapes; no code from the original project is vendored in to do it.
  The control backend's `CONTROL_BACKEND_URL` env var follows the same
  "point it at your own implementation" pattern (defaults to
  `http://localhost:8082`).

## What was stripped out of the original fork

- The ttyd terminal "flip side" of each chat card, and dockview-only tab
  navigation (subagent "view conversation" now just switches the sidebar
  selection instead of opening a workspace tab) — these were workspace-shell
  UI, not an external service, so there was nothing to keep documented here.
- The projects/plugin-slot layer from the original workspace shell (same
  reason).
- Per-service brand icons (Slack/GitHub/etc. logos on permission cards) —
  bundled artwork from the original project's monorepo, not something to
  vendor into this repo. Cards fall back to a generic icon.

## Tests

```
cd frontend && npm test
```
