"""Live click-through preview of the sign-up plan-selector redesign.

Serves the connector frontend's real built bundle
(``apps/remote_service_connector/frontend``, copied into
``assets/accounts_dist/`` -- rebuild + recopy after any source change; see
this app's README) behind an in-memory stub of the pages it needs
(``/login``, ``/signup``, ``/manage``, the static doc pages) and its JSON API
(``/accounts/api/*``), mirroring the routes the real backend
(``accounts_web.py``) serves. There is no real auth backend: sign-up/sign-in
always succeed and set a session cookie tracked in a module-level dict, so the
whole flow is clickable without SuperTokens, Turnstile, or a database.

Services run from /home/user/workspace (the repo root). Conventions:

- Persistent state (anything written and read across runs -- cursors,
  caches, snapshots, user records): read and write it under ``DATA_DIR``
  (defined below), never a hardcoded ``data/.apps/signup-preview/`` at the
  call site. ``DATA_DIR`` defaults to ``data/.apps/signup-preview/`` but
  honors the ``SIGNUP_PREVIEW_DATA_DIR`` env var, so an editing agent can point a
  throwaway instance at a *copy* of the data instead of the live store
  (see the update-app skill). Do NOT use ``Path(__file__)``-based
  paths for state -- the bug to avoid is one process writing to
  ``/home/user/workspace/data/.apps/...`` while another reads from
  ``/home/user/workspace/system/apps/<pkg>/data/...``.
- Static assets shipped alongside this file (templates, default
  configs, bundled JSON): ``Path(__file__).parent / "assets/..."`` is
  fine and is the right pattern. The copied bundle lives there.
- Listen port: bind ``PORT`` (defined below), which defaults to this
  app's assigned port but honors the ``SIGNUP_PREVIEW_PORT`` env var, so
  an editing agent can boot a throwaway instance on a *spare* port
  alongside the live one (see the update-app skill). Never hardcode
  the port at the ``run_simple`` call.

This is a synchronous Flask app served by the threaded Werkzeug server.
The app owns its own browser origin (the forwarder routes
``http://signup-preview.<workspace-host>/`` straight to this port), so it serves
at ``/`` and root-absolute URLs, cookies, and service workers all work
unmodified -- nothing rewrites anything.
"""

import os
import secrets
from urllib.parse import parse_qs
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file
from werkzeug.serving import run_simple

# Persistent state for this app lives under DATA_DIR. It defaults to
# ``data/.apps/signup-preview/`` but is overridable via the ``SIGNUP_PREVIEW_DATA_DIR`` env var
# so a throwaway instance can run against a *copy* of the data while editing --
# see the update-app skill. Always read/write state through DATA_DIR;
# never hardcode ``data/.apps/signup-preview/`` at a call site, or the override is
# bypassed. A writing call site should ``DATA_DIR.mkdir(parents=True,
# exist_ok=True)`` before writing.
DATA_DIR = Path(os.environ.get("SIGNUP_PREVIEW_DATA_DIR", "data/.apps/signup-preview"))

# Listen port. Defaults to this app's assigned port but is overridable via
# the ``SIGNUP_PREVIEW_PORT`` env var so an editing agent can boot a throwaway
# instance on a spare port next to the live one (see the update-app skill).
# Never hardcode the port at the ``run_simple`` call, or the override is bypassed.
PORT = int(os.environ.get("SIGNUP_PREVIEW_PORT", "8080"))

# The real built connector-frontend bundle, copied in from
# .external_worktrees/mngr/apps/remote_service_connector/frontend/dist -- see
# this app's README for the rebuild-and-recopy command.
_DIST_DIR = Path(__file__).parent / "assets" / "accounts_dist"

# Sessions: cookie value -> {"user_id", "email"}. In-memory only, no
# real auth backend -- sign-up/sign-in always succeed. Resets on restart.
_SESSIONS: dict[str, dict[str, str]] = {}
_SESSION_COOKIE = "preview_session"

app = Flask("signup_preview", static_folder=None)

# The location beacon, appended to every served HTML page (see the build-app
# skill): posts the current path to the parent workspace shell so it can
# reopen this app's window at the same place.
_LOCATION_BEACON = (
    '<script>if (window.parent !== window) window.parent.postMessage('
    '{type: "shell:location", path: location.pathname + location.search}, "*");</script>'
)


def _serve_dist_file(filename: str) -> Response:
    page_path = _DIST_DIR / filename
    if not page_path.is_file():
        return Response(
            f"<!doctype html><html><body><h1>Preview bundle missing: {filename}</h1>"
            "<p>Rebuild the connector frontend and recopy dist/ into this app's assets "
            "(see this app's README), then restart.</p></body></html>",
            status=503,
            mimetype="text/html",
        )
    if page_path.suffix == ".html":
        html = page_path.read_text()
        html = html.replace("</body>", f"{_LOCATION_BEACON}</body>")
        return Response(html, mimetype="text/html")
    return send_file(page_path)


@app.route("/")
@app.route("/login")
@app.route("/signup")
@app.route("/manage")
@app.route("/auth/reset-password")
@app.route("/auth/verify-email")
@app.route("/check-inbox")
@app.route("/downloads")
@app.route("/invite")
def spa_page() -> Response:
    return _serve_dist_file("index.html")


@app.route("/terms-of-service")
def terms_of_service() -> Response:
    return _serve_dist_file("terms-of-service.html")


@app.route("/code-of-conduct")
def code_of_conduct() -> Response:
    return _serve_dist_file("code-of-conduct.html")


@app.route("/privacy-policy")
def privacy_policy() -> Response:
    return _serve_dist_file("privacy-policy.html")


@app.route("/accounts/assets/<path:asset_path>")
def accounts_asset(asset_path: str) -> Response:
    assets_dir = (_DIST_DIR / "assets").resolve()
    candidate = (assets_dir / asset_path).resolve()
    if not candidate.is_relative_to(assets_dir) or not candidate.is_file():
        return Response("Not found", status=404)
    return send_file(candidate)


def _current_session() -> dict[str, str] | None:
    cookie = request.cookies.get(_SESSION_COOKIE)
    if cookie is None:
        return None
    return _SESSIONS.get(cookie)


def _page_query() -> dict[str, list[str]]:
    """The query string of the page that made this API call (from Referer).

    The SPA fetches its config without forwarding the page's query, so the
    preview reads it back from the same-origin Referer to pick a scenario.
    """
    return parse_qs(urlparse(request.headers.get("Referer", "")).query)


@app.route("/accounts/api/config")
def accounts_config() -> Response:
    # google_enabled=True so the preview matches the real default (Google
    # leads the sign-up tab) -- this is what Josh's review flagged as missing
    # from an earlier preview build.
    #
    # Preview-only scenarios, picked by the page's own query string:
    # ?waitlist=1 is the production default for a code-less signup (the
    # waitlist is on and no invite code is present); ?invite=<email> adds a
    # presented invite code for that email. Neither is the real backend's
    # contract -- the real config reads a cookie set by /invite/<code>.
    query = _page_query()
    invited_email = query.get("invite", [""])[0]
    is_waitlist_enabled = bool(invited_email) or query.get("waitlist", [""])[0] == "1"
    return jsonify(
        {
            "turnstile_site_key": "",
            "google_enabled": True,
            "waitlist_enabled": is_waitlist_enabled,
            "signup_code": {"email": invited_email, "pinned_plan": None} if invited_email else None,
        }
    )


@app.route("/accounts/api/downloads")
def accounts_downloads() -> Response:
    # The waitlist-off answer: the three installers, as the real API lists them.
    return jsonify(
        {
            "platforms": [
                {"platform": "mac-arm64", "label": "macOS (Apple silicon)", "url": "#"},
                {"platform": "linux-deb", "label": "Linux (.deb)", "url": "#"},
                {"platform": "linux-appimage", "label": "Linux (AppImage)", "url": "#"},
            ]
        }
    )


@app.route("/accounts/api/me")
def accounts_me() -> Response:
    session = _current_session()
    if session is None:
        return jsonify({"signed_in": False}), 401
    return jsonify(
        {
            "signed_in": True,
            "user_id": session["user_id"],
            "email": session["email"],
            "email_verified": True,
            "display_name": None,
            "profile_picture_url": None,
        }
    )


def _create_session(email: str) -> dict[str, Any]:
    cookie = secrets.token_hex(16)
    user_id = secrets.token_hex(8)
    _SESSIONS[cookie] = {"user_id": user_id, "email": email}
    resp = jsonify({"status": "OK", "user": {"user_id": user_id, "email": email}})
    resp.set_cookie(_SESSION_COOKIE, cookie, httponly=True, samesite="Strict")
    return resp


@app.route("/accounts/api/signup", methods=["POST"])
def accounts_signup() -> Response:
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip()
    password = str(body.get("password", ""))
    if not email or not password:
        return jsonify({"status": "FIELD_ERROR", "message": "Email and password are required"})
    return _create_session(email)


@app.route("/accounts/api/signin", methods=["POST"])
def accounts_signin() -> Response:
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip()
    password = str(body.get("password", ""))
    if not email or not password:
        return jsonify({"status": "FIELD_ERROR", "message": "Email and password are required"})
    return _create_session(email)


@app.route("/accounts/api/signout", methods=["POST"])
def accounts_signout() -> Response:
    cookie = request.cookies.get(_SESSION_COOKIE)
    if cookie is not None:
        _SESSIONS.pop(cookie, None)
    resp = jsonify({"status": "OK"})
    resp.delete_cookie(_SESSION_COOKIE)
    return resp


@app.route("/health")
def health() -> Response:
    return Response('{"status": "ok"}', mimetype="application/json")


def main() -> None:
    run_simple(
        "127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False
    )


if __name__ == "__main__":
    main()
