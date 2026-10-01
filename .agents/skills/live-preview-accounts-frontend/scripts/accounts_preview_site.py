"""Build each side from real source, and render the static preview site.

``build_side`` builds the frontend at one git ref in a throwaway worktree (the
mngr clone itself is never checked out or modified) and keeps the untouched
``dist/`` plus a provenance record. ``render_site`` loads every touched page
from each side's ``dist/`` in a headless browser on a fake origin -- every
request answered locally, API calls from ``assets/api_stubs.json`` -- and saves
the rendered DOM, scripts stripped, as a plain static HTML page.
"""

from __future__ import annotations

import html
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Route, sync_playwright

from accounts_preview_common import (
    DOC_PAGES,
    FRONTEND_PATH,
    PROD_BASE,
    SIDES,
    SKILL_DIR,
    PreviewError,
    Workspace,
    git,
    page_dir_name,
    page_label,
    page_state,
    resolve_commit,
    utc_now,
)

FORTRESS = "/opt/fortress/tilion-fortress/tilion"
API_STUBS = SKILL_DIR / "assets" / "api_stubs.json"
CAPTURE_ORIGIN = "http://accounts.preview.invalid"
VIEWPORT = {"width": 500, "height": 700}

# git worktree add/remove on one repository must not interleave.
_WORKTREE_LOCK = threading.Lock()


def launch_browser(playwright: Any) -> Any:
    if not Path(FORTRESS).exists():
        raise PreviewError(f"the Fortress browser is not installed at {FORTRESS} (see AGENTS.md)")
    return playwright.chromium.launch(executable_path=FORTRESS)


def fetch_origin(ws: Workspace) -> None:
    """Fetch ``origin`` in the mngr clone, through the latchkey gateway header when one is configured."""
    password = os.environ.get("LATCHKEY_GATEWAY_PASSWORD")
    extra = (f"http.extraHeader=X-Latchkey-Gateway-Password: {password}",) if password else ()
    git(ws.mngr_repo, "fetch", "--quiet", "origin", extra_config=extra)


def http_get(url: str, timeout: float = 20) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "live-preview-accounts-frontend"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def prod_deploy_id() -> str:
    """The deploy id prod's bundle was built with; baked into the JS, so the before side must match it."""
    status, body = http_get(f"{PROD_BASE}/version")
    if status != 200:
        raise PreviewError(f"{PROD_BASE}/version answered {status}")
    deploy_id = json.loads(body).get("deploy_id")
    if not deploy_id:
        raise PreviewError(f"{PROD_BASE}/version has no deploy_id")
    return str(deploy_id)


def _github_url(remote: str) -> str | None:
    """``https://github.com/org/repo`` from a remote, including one routed through the latchkey gateway."""
    match = re.search(r"(https://github\.com/[^/\s]+/[^/\s]+?)(?:\.git)?/?$", remote.strip())
    return match.group(1) if match else None


def _run_logged(command: list[str], cwd: Path, log: Path, env: dict[str, str]) -> None:
    with open(log, "a") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        handle.flush()
        proc = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, env=env, check=False)
    if proc.returncode != 0:
        lines = log.read_text().splitlines()
        tail = "\n".join(lines[-25:])
        raise PreviewError(f"{' '.join(command)} failed (exit {proc.returncode}); last output:\n{tail}")


def build_side(ws: Workspace, name: str, side: str, ref: str, deploy_id: str | None) -> dict[str, Any]:
    """Build the frontend at ``ref`` into ``data/.apps/<name>/builds/<side>/``; returns its provenance."""
    if side not in SIDES:
        raise PreviewError(f"side must be one of {SIDES}")
    commit = resolve_commit(ws.mngr_repo, ref)
    token = secrets.token_hex(4)
    worktree = ws.scratch / "worktrees" / f"{name}-{side}-{token}"
    final = ws.build_dir(name, side)
    staging = final.with_name(f".{side}.staging-{token}")
    staging.mkdir(parents=True)
    log = staging / "build.log"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    with _WORKTREE_LOCK:
        git(ws.mngr_repo, "worktree", "add", "--detach", "--quiet", str(worktree), commit)
    try:
        frontend = worktree / FRONTEND_PATH
        if not (frontend / "package.json").is_file():
            raise PreviewError(f"{FRONTEND_PATH} does not exist at {ref}")
        env = dict(os.environ)
        env.pop("MINDS_DEPLOY_ID", None)
        if deploy_id:
            env["MINDS_DEPLOY_ID"] = deploy_id
        _run_logged(["pnpm", "install", "--frozen-lockfile"], frontend, log, env)
        _run_logged(["pnpm", "run", "build"], frontend, log, env)
        shutil.copytree(frontend / "dist", staging / "dist")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        with _WORKTREE_LOCK:
            git(ws.mngr_repo, "worktree", "remove", "--force", str(worktree), check=False)
            git(ws.mngr_repo, "worktree", "prune", check=False)
        shutil.rmtree(worktree, ignore_errors=True)
        _remove_if_empty(worktree.parent, ws.scratch)
    remote = git(ws.mngr_repo, "remote", "get-url", "origin", check=False).strip()
    github = _github_url(remote)
    subject, committed_at = git(ws.mngr_repo, "log", "-1", "--format=%s%n%cI", commit).splitlines()[:2]
    provenance = {
        "side": side,
        "ref": ref,
        "commit": commit,
        "commit_subject": subject,
        "committed_at": committed_at,
        "commit_url": f"{github}/commit/{commit}" if github else None,
        "source_repo": github or remote,
        "frontend_path": FRONTEND_PATH,
        "deploy_id": deploy_id or "dev",
        "built_at": utc_now(),
    }
    (staging / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    _swap_in(staging, final)
    return provenance


def _remove_if_empty(*directories: Path) -> None:
    """Drop scratch directories once nothing is left in them (a parallel build may still be using one)."""
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            return


def _swap_in(staging: Path, final: Path) -> None:
    """Replace ``final`` with ``staging`` so a reader never sees a half-written directory."""
    old = final.with_name(f".{final.name}.old-{secrets.token_hex(4)}")
    if final.exists():
        os.rename(final, old)
    os.rename(staging, final)
    shutil.rmtree(old, ignore_errors=True)


def load_stubs() -> dict[str, dict[str, Any]]:
    stubs = json.loads(API_STUBS.read_text())
    return {state: answers for state, answers in stubs.items() if not state.startswith("_")}


# Runs in the captured page: point links at captured pages within the same side,
# then serialize the DOM with every script removed, so the page is inert HTML.
_SERIALIZE_JS = """([side, captured]) => {
  const root = document.documentElement.cloneNode(true);
  root.querySelectorAll('script, link[rel="modulepreload"]').forEach((node) => node.remove());
  root.querySelectorAll('a[href^="/"]').forEach((anchor) => {
    const url = new URL(anchor.getAttribute('href'), location.origin);
    if (captured.includes(url.pathname)) {
      anchor.setAttribute('href', '/' + side + url.pathname + '/' + url.search + url.hash);
    }
  });
  return '<!doctype html>\\n' + root.outerHTML + '\\n';
}"""


def capture_page(
    browser: Any, dist: Path, path: str, stubs: dict[str, dict[str, Any]], side: str, captured: list[str]
) -> dict[str, Any]:
    """Render one SPA page from ``dist`` and return its static HTML plus what happened while rendering."""
    answers = stubs[page_state(path)]
    unanswered: list[str] = []
    page_errors: list[str] = []

    def handle(route: Route) -> None:
        request = route.request
        url = request.url
        if not url.startswith(CAPTURE_ORIGIN + "/"):
            unanswered.append(f"{request.method} {url}")
            route.abort()
            return
        request_path = url[len(CAPTURE_ORIGIN) :].split("?", 1)[0].split("#", 1)[0]
        if request_path.startswith("/accounts/assets/"):
            asset = (dist / "assets" / request_path.removeprefix("/accounts/assets/")).resolve()
            if asset.is_relative_to((dist / "assets").resolve()) and asset.is_file():
                route.fulfill(path=str(asset))
                return
            unanswered.append(f"{request.method} {request_path}")
            route.fulfill(status=404, body="not in this bundle")
            return
        key = f"{request.method} {request_path}"
        if key in answers:
            answer = answers[key]
            route.fulfill(status=answer["status"], json=answer["body"])
            return
        if request_path.startswith("/accounts/"):
            unanswered.append(key)
            route.fulfill(status=500, json={"detail": "preview stub has no answer for this call"})
            return
        route.fulfill(path=str(dist / "index.html"), content_type="text/html")

    context = browser.new_context(viewport=VIEWPORT)
    try:
        context.route("**/*", handle)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(CAPTURE_ORIGIN + path, wait_until="networkidle", timeout=30000)
        page.wait_for_function("document.getElementById('app')?.children.length > 0", timeout=10000)
        page.wait_for_timeout(300)
        final_path = page.url[len(CAPTURE_ORIGIN) :] if page.url.startswith(CAPTURE_ORIGIN) else page.url
        static_html = page.evaluate(_SERIALIZE_JS, [side, captured])
    finally:
        context.close()
    return {"html": static_html, "final_path": final_path, "unanswered": unanswered, "page_errors": page_errors}


def render_site(ws: Workspace, name: str, pages: list[str]) -> dict[str, Any]:
    """Write ``data/.apps/<name>/site/`` from both sides' builds; returns the render manifest."""
    provenance = load_provenance(ws, name)
    final = ws.site_dir(name)
    staging = final.with_name(f".site.staging-{secrets.token_hex(4)}")
    assets = staging / "accounts" / "assets"
    assets.mkdir(parents=True)
    stubs = load_stubs()
    spa_pages = [path for path in pages if path not in DOC_PAGES]
    captured = sorted(set(pages) | set(DOC_PAGES))
    manifest: dict[str, Any] = {"rendered_at": utc_now(), "pages": pages, "sides": {}}
    problems: list[str] = []
    try:
        for side in SIDES:
            dist = ws.build_dir(name, side) / "dist"
            for asset in (dist / "assets").iterdir():
                shutil.copy2(asset, assets / asset.name)
            for doc_path in DOC_PAGES:
                source = dist / f"{doc_path.strip('/')}.html"
                if source.is_file():
                    target = staging / side / page_dir_name(doc_path) / "index.html"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            raw = staging / "_raw" / side
            shutil.copytree(dist, raw / "dist")
            shutil.copy2(ws.build_dir(name, side) / "provenance.json", raw / "provenance.json")
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                for side in SIDES:
                    dist = ws.build_dir(name, side) / "dist"
                    side_manifest: dict[str, Any] = {}
                    for path in spa_pages:
                        result = capture_page(browser, dist, path, stubs, side, captured)
                        target = staging / side / page_dir_name(path) / "index.html"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(result["html"])
                        side_manifest[path] = {key: value for key, value in result.items() if key != "html"}
                        for call in result["unanswered"]:
                            problems.append(f"{side} {path}: unanswered request {call}")
                        for error in result["page_errors"]:
                            problems.append(f"{side} {path}: script error {error}")
                    manifest["sides"][side] = side_manifest
            finally:
                browser.close()
        if problems:
            raise PreviewError("rendering hit problems:\n  " + "\n  ".join(problems))
        shutil.copy2(API_STUBS, staging / "_raw" / "api_stubs.json")
        (staging / "_raw" / "render.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (staging / "index.html").write_text(render_index(name, pages, provenance, None))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _swap_in(staging, final)
    return manifest


def load_provenance(ws: Workspace, name: str) -> dict[str, dict[str, Any]]:
    provenance: dict[str, dict[str, Any]] = {}
    for side in SIDES:
        build = ws.build_dir(name, side)
        if not (build / "dist" / "index.html").is_file():
            raise PreviewError(f"no {side} build for {name!r} -- run the build step first")
        provenance[side] = json.loads((build / "provenance.json").read_text())
    return provenance


def write_index(ws: Workspace, name: str, pages: list[str], report: dict[str, Any] | None, review: dict[str, Any] | None) -> None:
    """Rewrite the served index page in place, e.g. once the checks have run."""
    index = ws.site_dir(name) / "index.html"
    temp = index.with_name(f".index.html.{secrets.token_hex(4)}")
    temp.write_text(render_index(name, pages, load_provenance(ws, name), report, review))
    os.replace(temp, index)


def side_url(side: str, path: str) -> str:
    return f"/{side}/{page_dir_name(path)}/"


def _commit_link(provenance: dict[str, Any]) -> str:
    short = html.escape(provenance["commit"][:10])
    ref = html.escape(provenance["ref"])
    if provenance.get("commit_url"):
        return f'<code>{ref}</code> at <a href="{html.escape(provenance["commit_url"])}"><code>{short}</code></a>'
    return f"<code>{ref}</code> at <code>{short}</code>"


def render_index(
    name: str,
    pages: list[str],
    provenance: dict[str, dict[str, Any]],
    report: dict[str, Any] | None,
    review: dict[str, Any] | None = None,
) -> str:
    """The preview's front page: the comparison table and, once verified, the side-by-side screenshots."""
    rows = []
    for path in pages:
        prod = f"{PROD_BASE}{path}"
        rows.append(
            "<tr>"
            f"<td>{html.escape(page_label(path))}<div class=path>{html.escape(path)}</div></td>"
            f'<td><a href="{html.escape(prod)}">prod</a></td>'
            f'<td><a href="{side_url("before", path)}">before</a></td>'
            f'<td><a href="{side_url("after", path)}">after</a></td>'
            "</tr>"
        )
    status = '<p class="status pending">Not checked yet.</p>'
    sheets = ""
    if report is not None:
        failures = report.get("failures", [])
        warnings = report.get("warnings", [])
        if failures:
            items = "".join(f"<li>{html.escape(item)}</li>" for item in failures)
            status = f'<div class="status fail"><strong>Checks failed</strong> ({html.escape(report["checked_at"])})<ul>{items}</ul></div>'
        else:
            status = f'<p class="status pass">All checks passed ({html.escape(report["checked_at"])}).</p>'
        if warnings:
            items = "".join(f"<li>{html.escape(item)}</li>" for item in warnings)
            status += f'<div class="status warn"><strong>Notes</strong><ul>{items}</ul></div>'
        figures = []
        for path in pages:
            entry = report.get("pages", {}).get(path)
            if entry and entry.get("sheet"):
                figures.append(
                    f'<figure><figcaption>{html.escape(page_label(path))}</figcaption>'
                    f'<a href="/_raw/verify/{entry["sheet"]}"><img loading="lazy" src="/_raw/verify/{entry["sheet"]}" alt=""></a></figure>'
                )
        sheets = "<h2>Side by side</h2><p class=muted>Left to right: prod, before, after.</p>" + "".join(figures)
    if review is not None:
        verdict = "passed" if review.get("passed") else "did not pass"
        status += f'<p class="muted">Visual review against the intended change {verdict}: &ldquo;{html.escape(review.get("intent", ""))}&rdquo;.</p>'
    before, after = provenance["before"], provenance["after"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview: {html.escape(name)}</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1.5rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2.5rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #e5e5e5; vertical-align: top; }}
  th {{ font-weight: 600; color: #555; }}
  .path {{ font: 12px ui-monospace, monospace; color: #888; }}
  .muted {{ color: #777; }}
  .status {{ padding: .6rem .9rem; border-radius: 6px; margin: 1rem 0; }}
  .status ul {{ margin: .3rem 0 0; }}
  .pass {{ background: #eef8ef; }} .fail {{ background: #fdecec; }} .warn {{ background: #fff7e0; }} .pending {{ background: #f3f3f3; }}
  figure {{ margin: 1.5rem 0; }} figcaption {{ font-weight: 600; margin-bottom: .4rem; }}
  figure img {{ max-width: 100%; border: 1px solid #e5e5e5; }}
  footer {{ margin-top: 3rem; font-size: 13px; color: #888; }} footer a {{ color: #888; }}
  a {{ color: #0b63ce; }}
</style>
</head>
<body>
<h1>Before / after preview: {html.escape(name)}</h1>
<p class="muted">Static snapshots of accounts.imbue.com built from the real source. Before: {_commit_link(before)}. After: {_commit_link(after)}.</p>
{status}
<table>
<thead><tr><th>Page</th><th>Before (prod)</th><th>Before (preview)</th><th>After (preview)</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
{sheets}
<footer>Source records: <a href="/_raw/before/provenance.json">before build</a> &middot;
<a href="/_raw/after/provenance.json">after build</a> &middot;
<a href="/_raw/before/dist/">before bundle</a> &middot; <a href="/_raw/after/dist/">after bundle</a> &middot;
<a href="/_raw/api_stubs.json">API answers used</a> &middot; <a href="/_raw/render.json">render log</a>
{' &middot; <a href="/_raw/verify/report.json">check report</a>' if report is not None else ''}</footer>
</body>
</html>
"""
