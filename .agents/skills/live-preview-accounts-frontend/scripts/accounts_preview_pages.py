"""Which accounts.imbue.com pages a change touches.

The files changed between the two refs are traced through the frontend's
TypeScript imports (as of the after ref) up to the page modules ``index.ts``
mounts, then mapped to routes through ``index.ts``'s ``PAGE_BY_PATH`` table.
Anything that is not reached through a page module -- the stylesheet, fonts,
``index.ts`` itself, build config -- can affect every page, so it maps to all
of them. A file in ``public/`` maps to that document page.

The parsing half (``discover_pages``) is pure, over file contents, so it is
tested on fixtures; ``read_change`` gathers those contents from git.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from accounts_preview_common import (
    DOC_PAGES,
    FALLBACK_ROUTES,
    FRONTEND_PATH,
    PreviewError,
    git,
)

_ENTRY = "src/index.ts"

# `import x from "./y"`, `import { a, b } from "./y"`, `export ... from "./y"`,
# `import "./y.css"` -- relative specifiers only; packages ("mithril") are not ours.
_IMPORT_FROM = re.compile(
    r"""(?:^|\s|;)(?:import|export)\s[^;]*?\sfrom\s*["'](\.{1,2}/[^"']+)["']""", re.S
)
_BARE_IMPORT = re.compile(r"""(?:^|\s|;)import\s*["'](\.{1,2}/[^"']+)["']""")
_NAMED_IMPORT = re.compile(
    r"""import\s*\{([^}]*)\}\s*from\s*["'](\.{1,2}/[^"']+)["']""", re.S
)
_PAGE_TABLE = re.compile(r"PAGE_BY_PATH[^{;]*\{(.*?)\};", re.S)
_PAGE_ENTRY = re.compile(r"""["'](/[^"']*)["']\s*:\s*(\w+)""")
_FALLBACK = re.compile(r"PAGE_BY_PATH\[[^\]]*\]\s*\?\?\s*(\w+)")


def _resolve(importer: str, specifier: str, files: Iterable[str]) -> str | None:
    """The repo file a relative import names (``./api`` -> ``src/api.ts``), or None when not ours."""
    known = set(files)
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
    for candidate in (base, f"{base}.ts", f"{base}.tsx", f"{base}/index.ts"):
        if candidate in known:
            return candidate
    return None


def import_graph(sources: Mapping[str, str]) -> dict[str, set[str]]:
    """``module -> modules it imports``, over the relative imports of every .ts source."""
    graph: dict[str, set[str]] = {}
    for path, text in sources.items():
        if not path.endswith((".ts", ".tsx")):
            continue
        targets: set[str] = set()
        for pattern in (_IMPORT_FROM, _BARE_IMPORT):
            for match in pattern.finditer(text):
                resolved = _resolve(path, match.group(1), sources)
                if resolved is not None:
                    targets.add(resolved)
        graph[path] = targets
    return graph


def page_modules(sources: Mapping[str, str]) -> dict[str, list[str]]:
    """``page module -> routes it serves``, read from index.ts's route table and fallback."""
    entry = sources.get(_ENTRY)
    if entry is None:
        raise PreviewError(f"{FRONTEND_PATH}/{_ENTRY} is missing at the after ref")
    module_by_component: dict[str, str] = {}
    for match in _NAMED_IMPORT.finditer(entry):
        resolved = _resolve(_ENTRY, match.group(2), sources)
        if resolved is None:
            continue
        for name in match.group(1).split(","):
            component = name.strip().split(" as ")[-1].strip()
            if component:
                module_by_component[component] = resolved
    table = _PAGE_TABLE.search(entry)
    if table is None:
        raise PreviewError(
            "could not find PAGE_BY_PATH in index.ts -- the frontend's routing changed; pass --pages"
        )
    routes_by_module: dict[str, list[str]] = {}
    for route, component in _PAGE_ENTRY.findall(table.group(1)):
        module = module_by_component.get(component)
        if module is None:
            raise PreviewError(
                f"index.ts routes {route} to {component}, whose import was not found; pass --pages"
            )
        routes_by_module.setdefault(module, []).append(route)
    fallback = _FALLBACK.search(entry)
    if fallback is not None and fallback.group(1) in module_by_component:
        routes_by_module.setdefault(module_by_component[fallback.group(1)], []).extend(
            FALLBACK_ROUTES
        )
    return routes_by_module


def _importers_closure(graph: Mapping[str, set[str]], start: str) -> set[str]:
    """``start`` plus every module that imports it, directly or transitively."""
    reverse: dict[str, set[str]] = {}
    for module, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(module)
    seen = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for importer in reverse.get(current, set()):
            if importer not in seen:
                seen.add(importer)
                frontier.append(importer)
    return seen


def discover_pages(
    changed: Iterable[str], sources: Mapping[str, str]
) -> tuple[list[str], dict[str, list[str]]]:
    """The routes a change touches, and why: ``(routes, reasons_by_changed_file)``.

    ``changed`` and the keys of ``sources`` are paths relative to the frontend
    directory; ``sources`` holds the after ref's ``src/`` files (any file
    missing from it is treated as deleted and skipped -- whoever imported it
    changed too, and is traced instead).
    """
    graph = import_graph(sources)
    routes_by_module = page_modules(sources)
    every_route = sorted(
        {route for routes in routes_by_module.values() for route in routes}
    )
    touched: set[str] = set()
    reasons: dict[str, list[str]] = {}
    for path in sorted(set(changed)):
        if path.startswith("public/"):
            doc_route = "/" + posixpath.splitext(posixpath.basename(path))[0]
            hit = [doc_route] if doc_route in DOC_PAGES else every_route
        elif path.startswith("src/") and path not in sources:
            reasons[path] = []
            continue
        elif path.startswith("src/") and path.endswith((".ts", ".tsx", ".css")):
            closure = _importers_closure(graph, path)
            hit = sorted(
                {
                    route
                    for module in closure
                    for route in routes_by_module.get(module, [])
                }
            )
            if not hit:
                hit = every_route
        else:
            hit = every_route
        reasons[path] = hit
        touched.update(hit)
    return sorted(touched, key=route_sort_key), reasons


_PREFERRED_ORDER = ("/login", "/signup", "/manage", "/downloads", "/invite")


def route_sort_key(route: str) -> tuple[int, str]:
    """The table's row order: the main pages first, then the rest, then the documents."""
    if route in _PREFERRED_ORDER:
        return (_PREFERRED_ORDER.index(route), route)
    if route in DOC_PAGES:
        return (2000, route)
    return (1000, route)


def read_change(
    mngr_repo: Path, before_commit: str, after_commit: str
) -> tuple[list[str], dict[str, str]]:
    """The frontend files changed in ``before...after`` and the after ref's ``src/`` sources, from git."""
    prefix = f"{FRONTEND_PATH}/"
    changed = [
        line[len(prefix) :]
        for line in git(
            mngr_repo,
            "diff",
            "--name-only",
            "--no-renames",
            f"{before_commit}...{after_commit}",
            "--",
            prefix,
        ).splitlines()
        if line.startswith(prefix)
    ]
    listed = git(
        mngr_repo, "ls-tree", "-r", "--name-only", after_commit, "--", f"{prefix}src/"
    ).splitlines()
    sources: dict[str, str] = {}
    for full in listed:
        relative = full[len(prefix) :]
        if relative.endswith((".ts", ".tsx", ".css")):
            sources[relative] = git(mngr_repo, "show", f"{after_commit}:{full}")
        else:
            sources[relative] = ""
    return changed, sources
