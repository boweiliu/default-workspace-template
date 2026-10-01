"""Page discovery, over the real frontend's import graph (fixture) and over small hand-made graphs."""

import json
import subprocess
from pathlib import Path

import pytest
from conftest import FIXTURES

from accounts_preview_common import FRONTEND_PATH, PreviewError
from accounts_preview_pages import discover_pages, import_graph, page_modules, read_change

SOURCES = json.loads((FIXTURES / "frontend_sources.json").read_text())["sources"]
SPA_ROUTES = [
    "/login",
    "/signup",
    "/manage",
    "/downloads",
    "/invite",
    "/app-stopped-waiting",
    "/auth/reset-password",
    "/auth/verify-email",
    "/check-inbox",
]


def test_page_modules_reads_the_route_table_and_the_fallback() -> None:
    assert page_modules(SOURCES) == {
        "src/ManagePage.ts": ["/manage"],
        "src/DownloadsPage.ts": ["/downloads"],
        "src/InvitePage.ts": ["/invite"],
        "src/UtilityPages.ts": ["/auth/reset-password", "/auth/verify-email", "/check-inbox", "/app-stopped-waiting"],
        "src/AuthPage.ts": ["/login", "/signup"],
    }


def test_import_graph_resolves_relative_imports_and_the_stylesheet() -> None:
    graph = import_graph(SOURCES)
    assert graph["src/plans.ts"] == {"src/components.ts"}
    assert "src/style.css" in graph["src/index.ts"]
    assert "src/plans.ts" in graph["src/AuthPage.ts"]


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        (["src/DownloadsPage.ts"], ["/downloads"]),
        (["src/ManagePage.ts"], ["/manage"]),
        (["src/flow.ts"], ["/login", "/signup"]),
        (["src/plans.ts"], ["/login", "/signup", "/downloads"]),
        (["src/UtilityPages.ts"], ["/app-stopped-waiting", "/auth/reset-password", "/auth/verify-email", "/check-inbox"]),
        (["public/privacy-policy.html"], ["/privacy-policy"]),
        (["src/DownloadsPage.ts", "public/terms-of-service.html"], ["/downloads", "/terms-of-service"]),
    ],
)
def test_a_change_maps_to_exactly_the_pages_that_import_it(changed: list[str], expected: list[str]) -> None:
    assert discover_pages(changed, SOURCES)[0] == expected


@pytest.mark.parametrize(
    "changed",
    [
        ["src/components.ts"],
        ["src/api.ts"],
        ["src/style.css"],
        ["src/fonts/abcdiatype-mono-400.woff2"],
        ["src/index.ts"],
        ["vite.config.ts"],
        ["package.json"],
        ["public/favicon.svg"],
    ],
)
def test_shared_files_map_to_every_spa_page(changed: list[str]) -> None:
    assert discover_pages(changed, SOURCES)[0] == SPA_ROUTES


def test_the_studio_wordmark_change_maps_to_every_page_with_reasons() -> None:
    changed = [
        "src/AuthPage.ts",
        "src/ManagePage.ts",
        "src/components.ts",
        "src/style.css",
    ]
    routes, reasons = discover_pages(changed, SOURCES)
    assert routes == SPA_ROUTES
    assert reasons["src/AuthPage.ts"] == ["/login", "/signup"]
    assert reasons["src/ManagePage.ts"] == ["/manage"]


def test_a_deleted_module_is_skipped_since_its_importers_changed_too() -> None:
    routes, reasons = discover_pages(["src/gone.ts", "src/DownloadsPage.ts"], SOURCES)
    assert routes == ["/downloads"]
    assert reasons["src/gone.ts"] == []


def test_a_frontend_without_the_route_table_fails_loudly() -> None:
    broken = dict(SOURCES, **{"src/index.ts": 'import m from "mithril";\nm.mount(document.body, {view: () => "x"});\n'})
    with pytest.raises(PreviewError, match="PAGE_BY_PATH"):
        discover_pages(["src/api.ts"], broken)


def _commit(repo: Path, files: dict[str, str], message: str) -> str:
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", message],
        check=True,
    )
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def test_read_change_takes_the_merge_base_diff_from_git(tmp_path: Path) -> None:
    repo = tmp_path / "mngr"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    base_files = {f"{FRONTEND_PATH}/{path}": text for path, text in SOURCES.items()}
    _commit(repo, base_files, "base")
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "feature"], check=True)
    after = _commit(repo, {f"{FRONTEND_PATH}/src/DownloadsPage.ts": SOURCES["src/DownloadsPage.ts"] + "// tweak\n"}, "tweak")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    # main moves on after the branch point; the merge-base diff must not pick this up.
    main_tip = _commit(repo, {f"{FRONTEND_PATH}/src/ManagePage.ts": SOURCES["src/ManagePage.ts"] + "// later\n"}, "later")
    changed, sources = read_change(repo, main_tip, after)
    assert changed == ["src/DownloadsPage.ts"]
    assert discover_pages(changed, sources)[0] == ["/downloads"]
