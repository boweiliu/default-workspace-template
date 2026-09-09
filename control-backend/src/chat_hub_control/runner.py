"""Control-plane backend for chat-hub-alt.

chat-hub-alt's own UI (see ../../frontend) talks to whatever chat backend
you point its dev server's /api proxy at (see frontend/vite.config.ts and
its README). This process is a separate, small backend with exactly one
job: let something else on this machine (a script, another program) tell
every open chat-hub-alt tab which chat to show.

A connected browser tab opens a WebSocket to /ws and is added to _clients.
POST /select-agent broadcasts the given agent id to every connected client,
which switches its own view -- no page reload. No auth, no origin check,
in-memory only (a restart drops all connections; tabs reconnect on their
own with backoff).
"""

import json
import logging
import os
import threading

from flask import Flask, Response, request
from flask_sock import Sock
from werkzeug.serving import run_simple

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("chat_hub_control")

PORT = int(os.environ.get("CHAT_HUB_CONTROL_PORT", "8082"))

app = Flask("chat_hub_control", static_folder=None)
sock = Sock(app)

_clients_lock = threading.Lock()
_clients: set = set()


@app.route("/")
def index() -> Response:
    return Response(
        "<!doctype html><html><body>chat-hub-alt control backend -- see /health</body></html>",
        mimetype="text/html",
    )


@app.route("/health")
def health() -> Response:
    return Response('{"status": "ok"}', mimetype="application/json")


@sock.route("/ws")
def ws(connection) -> None:
    with _clients_lock:
        _clients.add(connection)
        count = len(_clients)
    logger.info("tab connected (now %d connected)", count)
    try:
        while True:
            # Clients don't send anything meaningful; blocking on receive is
            # just how we notice a disconnect (raises when the socket closes).
            connection.receive()
    except Exception as exc:
        logger.info("tab disconnected: %s", exc)
    finally:
        with _clients_lock:
            _clients.discard(connection)
            count = len(_clients)
        logger.info("tab removed (now %d connected)", count)


@app.route("/select-agent", methods=["POST"])
def select_agent() -> Response:
    body = request.get_json(silent=True) or {}
    agent_id = body.get("agentId")
    if not isinstance(agent_id, str) or not agent_id:
        logger.warning("rejected select-agent request with no agentId: %r", body)
        return Response('{"error": "agentId is required"}', status=400, mimetype="application/json")

    message = json.dumps({"type": "select-agent", "agentId": agent_id})
    with _clients_lock:
        clients = list(_clients)
    sent = 0
    for connection in clients:
        try:
            connection.send(message)
            sent += 1
        except Exception as exc:
            logger.info("dropping dead client during broadcast: %s", exc)
            with _clients_lock:
                _clients.discard(connection)

    logger.info("select-agent %s -> sent to %d/%d connected tab(s)", agent_id, sent, len(clients))
    return Response(json.dumps({"sent_to": sent}), mimetype="application/json")


def main() -> None:
    logger.info("chat-hub-alt control backend starting on 127.0.0.1:%d", PORT)
    run_simple("127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False)


if __name__ == "__main__":
    main()
