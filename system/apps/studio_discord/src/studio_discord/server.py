"""The Studio Discord window: join the Imbue Studio Discord, and read it from inside Studio.

Runs from the workspace root (supervisord's working directory). Two settings, both overridable so a throwaway
instance can run beside the live one:

- ``STUDIO_DISCORD_DATA_DIR`` -- persistent state; defaults to ``data/.apps/studio-discord`` (the workspace's
  per-app data convention).
- ``STUDIO_DISCORD_PORT`` / ``STUDIO_DISCORD_HOST`` -- where to listen; loopback by default.
"""

import os
from pathlib import Path

from flask import Flask, Response, abort
from werkzeug.serving import run_simple

from studio_discord import studio

DATA_DIR = Path(os.environ.get("STUDIO_DISCORD_DATA_DIR", "data/.apps/studio-discord"))
PORT = int(os.environ.get("STUDIO_DISCORD_PORT", "8086"))
HOST = os.environ.get("STUDIO_DISCORD_HOST", "127.0.0.1")
ASSETS = Path(__file__).parent / "assets"

# Every page carries this: it connects the page to the shell framing it (so the shell reopens the window where
# it was) and installs the element context menu. Outside the shell it runs harmlessly.
SHELL_PAGE_SCRIPT = """<script type="module">
  import { connectToShell } from "/_static/app_contract.js";
  import { installElementContextMenu } from "/_static/context_menu.js";
  let handshake = null;
  const connection = connectToShell({
    onHandshake: (received) => {
      handshake = received;
      connection.location(location.pathname + location.search, document.title);
    },
  });
  installElementContextMenu({ connection, handshake: () => handshake });
</script>"""

app = Flask("studio_discord", static_folder=None)


@app.route("/")
def index() -> Response:
    # The confirmed look-and-feel mock (static sample data); the real data replaces it next.
    page = (
        (ASSETS / "mock.html")
        .read_text()
        .replace("__WIDGET_SAMPLE__", (ASSETS / "mock_widget.json").read_text())
        .replace("__SHELL_PAGE_SCRIPT__", SHELL_PAGE_SCRIPT)
    )
    return Response(page, mimetype="text/html")


@app.route("/_static/<name>")
def shell_module(name: str) -> Response:
    if name not in studio.SHELL_MODULE_NAMES:
        abort(404)
    try:
        body = studio.fetch_shell_module(name)
    except studio.ShellUnavailableError:
        abort(502)
    return Response(body, mimetype="text/javascript")


@app.route("/health")
def health() -> Response:
    return Response('{"status": "ok"}', mimetype="application/json")


def main() -> None:
    run_simple(HOST, PORT, app, threaded=True, use_reloader=False, use_debugger=False)


if __name__ == "__main__":
    main()
