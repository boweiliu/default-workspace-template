"""Building (its failure cleanup), capturing a page as static HTML, and the index page."""

import json
import subprocess
from pathlib import Path

import pytest

from accounts_preview_common import FRONTEND_PATH, PreviewError, Workspace
from accounts_preview_site import _github_url, build_side, capture_page, load_stubs, render_index

# Browser tests get a generous timeout: rendering a page takes seconds under gVisor.
needs_browser = pytest.mark.timeout(60)

# A stand-in for the accounts bundle: asks the API who is signed in and renders
# the answer plus links, the way the real SPA's pages do.
_APP_JS = """
const app = document.getElementById('app');
fetch('/accounts/api/me').then(async (resp) => {
  const body = await resp.json();
  const who = body.signed_in ? 'Signed in as ' + body.email : 'Signed out';
  app.innerHTML = '<h1>' + who + '</h1><a href="/downloads?x=1">downloads</a> <a href="/terms-of-service">terms</a>'
    + ' <a href="/accounts/oauth/google/start">google</a> <a href="/not-captured">other</a>';
});
"""


def _dist(tmp_path: Path, extra_js: str = "") -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "index-abc.js").write_text(_APP_JS + extra_js)
    (dist / "assets" / "index-abc.css").write_text("h1 { color: rgb(1, 2, 3); }")
    (dist / "index.html").write_text(
        '<!doctype html><html><head><script type="module" src="/accounts/assets/index-abc.js"></script>'
        '<link rel="stylesheet" href="/accounts/assets/index-abc.css"></head><body><div id="app"></div></body></html>'
    )
    return dist


def _capture(browser, dist: Path, path: str) -> dict:
    return capture_page(browser, dist, path, load_stubs(), "after", ["/downloads", "/login", "/terms-of-service"])


@needs_browser
def test_capture_saves_the_rendered_dom_as_inert_html_with_links_kept_in_side(browser, tmp_path: Path) -> None:
    result = _capture(browser, _dist(tmp_path), "/login")
    page = result["html"]
    assert "<h1>Signed out</h1>" in page
    assert "<script" not in page
    assert 'href="/accounts/assets/index-abc.css"' in page
    assert 'href="/after/downloads/?x=1"' in page
    assert 'href="/after/terms-of-service/"' in page
    assert 'href="/accounts/oauth/google/start"' in page
    assert 'href="/not-captured"' in page
    assert result["unanswered"] == []
    assert result["page_errors"] == []
    assert result["final_path"] == "/login"


@needs_browser
def test_signed_in_views_are_captured_as_the_sample_account(browser, tmp_path: Path) -> None:
    result = _capture(browser, _dist(tmp_path), "/manage")
    assert "<h1>Signed in as preview@example.com</h1>" in result["html"]


@needs_browser
def test_an_api_call_with_no_stubbed_answer_is_reported(browser, tmp_path: Path) -> None:
    result = _capture(browser, _dist(tmp_path, "fetch('/accounts/api/brand-new');"), "/login")
    assert result["unanswered"] == ["GET /accounts/api/brand-new"]


@needs_browser
def test_a_script_error_is_reported(browser, tmp_path: Path) -> None:
    result = _capture(browser, _dist(tmp_path, "setTimeout(() => { throw new Error('boom'); }, 0);"), "/login")
    assert any("boom" in error for error in result["page_errors"])


def test_stubs_answer_the_calls_the_real_frontend_makes_in_both_states() -> None:
    stubs = load_stubs()
    assert set(stubs) == {"signed_out", "signed_in"}
    for answers in stubs.values():
        assert {"GET /accounts/api/config", "GET /accounts/api/me", "GET /accounts/api/downloads"} <= set(answers)
        assert answers["GET /accounts/api/config"]["body"]["turnstile_site_key"] == ""
    assert stubs["signed_out"]["GET /accounts/api/me"] == {"status": 401, "body": {"signed_in": False}}
    assert stubs["signed_in"]["GET /accounts/api/me"]["body"]["email"] == "preview@example.com"


def test_github_url_reads_a_remote_routed_through_the_gateway() -> None:
    gateway = "http://host.docker.internal:1989/gateway/https://github.com/imbue-ai/mngr-internal.git"
    assert _github_url(gateway) == "https://github.com/imbue-ai/mngr-internal"
    assert _github_url("git@github.com:imbue-ai/mngr-internal.git") is None


def test_a_failed_build_leaves_no_worktree_and_no_partial_bundle(workspace: Workspace) -> None:
    repo = workspace.mngr_repo
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "README").write_text("no frontend here\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "x"], check=True
    )
    with pytest.raises(PreviewError, match=f"{FRONTEND_PATH} does not exist"):
        build_side(workspace, "x-preview", "after", "main", None)
    worktrees = subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True).stdout
    assert len(worktrees.splitlines()) == 1
    assert not workspace.scratch.exists()
    assert not (workspace.app_dir("x-preview") / "builds").exists() or not any(
        (workspace.app_dir("x-preview") / "builds").iterdir()
    )


def test_an_unknown_ref_fails_before_touching_anything(workspace: Workspace) -> None:
    subprocess.run(["git", "init", "-q", str(workspace.mngr_repo)], check=True)
    with pytest.raises(PreviewError, match="unknown git ref 'origin/nope'"):
        build_side(workspace, "x-preview", "after", "origin/nope", None)
    assert not workspace.app_dir("x-preview").exists()


def _provenance(side: str) -> dict:
    return {
        "side": side,
        "ref": "origin/main" if side == "before" else "origin/feature",
        "commit": ("a" if side == "before" else "b") * 40,
        "commit_url": f"https://github.com/imbue-ai/mngr-internal/commit/{'a' * 40}",
    }


def test_index_lists_every_page_with_its_three_links() -> None:
    page = render_index("x-preview", ["/login", "/manage"], {"before": _provenance("before"), "after": _provenance("after")}, None)
    assert "Before / after preview: x-preview" in page
    assert '<a href="https://accounts.imbue.com/login">prod</a>' in page
    assert '<a href="/before/login/">before</a>' in page
    assert '<a href="/after/manage/">after</a>' in page
    assert "Account management (signed in)" in page
    assert "Not checked yet." in page
    assert 'href="/_raw/before/provenance.json"' in page


def test_index_shows_failures_notes_sheets_and_the_review() -> None:
    report = {
        "checked_at": "2026-09-30T00:00:00Z",
        "failures": ["Sign in (after) did not load"],
        "warnings": ["Check inbox: before and after look identical"],
        "pages": {"/login": {"sheet": "login.sheet.png"}},
    }
    review = {"passed": True, "intent": "the wordmark reads <studio>"}
    page = render_index("x-preview", ["/login"], {"before": _provenance("before"), "after": _provenance("after")}, report, review)
    assert "Checks failed" in page and "Sign in (after) did not load" in page
    assert "before and after look identical" in page
    assert 'src="/_raw/verify/login.sheet.png"' in page
    assert "the wordmark reads &lt;studio&gt;" in page
    assert 'href="/_raw/verify/report.json"' in page
    json.dumps(report)
