# chat-hub-control

A tiny, dependency-light Flask backend with one job: let another process on
this machine tell every open chat-hub-alt browser tab which chat to show.

## Run it

```
pip install -e .
chat-hub-control
```

Listens on `127.0.0.1:8082` by default (override with `CHAT_HUB_CONTROL_PORT`).

## Use it

Each open chat-hub-alt tab holds a WebSocket to `/ws`. To switch every open
tab to a given chat:

```
curl -X POST http://127.0.0.1:8082/select-agent \
  -H "Content-Type: application/json" \
  -d '{"agentId": "<the id chat-hub-alt shows in its sidebar>"}'
```

No auth, no origin check, in-memory only (a restart drops all connections;
tabs reconnect on their own). This is a proof of concept for "tell the UI
which window to show" style control -- harden it (auth, origin checks,
connection liveness) before it carries anything that matters.
