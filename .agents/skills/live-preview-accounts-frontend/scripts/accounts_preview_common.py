"""Shared paths, page catalog, and per-preview state for live-preview-accounts-frontend.

Everything one preview owns lives under ``<root>/data/.apps/<name>/``:

- ``state.json`` -- refs, commits, pages, port, check results (not served).
- ``builds/<side>/`` -- each side's untouched ``dist/`` plus ``provenance.json``.
- ``site/`` -- what the preview app serves: the index page, ``before/`` and
  ``after/`` static pages, the shared ``accounts/assets/``, and ``_raw/``
  (the bundles, provenance, API stubs, and verification output).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

SKILL_NAME = "live-preview-accounts-frontend"
SKILL_DIR = Path(__file__).absolute().parents[1]
DEFAULT_ROOT = Path(__file__).absolute().parents[4]

FRONTEND_PATH = "apps/remote_service_connector/frontend"
PROD_BASE = "https://accounts.imbue.com"
SIDES = ("before", "after")

# Every view the accounts SPA serves, with the label a reviewer reads and the
# API state it is captured in. /manage and /downloads only make sense signed
# in (signed out, both send the visitor to sign in), so they are captured as a
# sample account; everything else is captured as prod shows it to a signed-out
# visitor. A route the frontend gains later is still discovered (from
# index.ts) and captured signed out under its path as its label.
PAGE_CATALOG: dict[str, tuple[str, str]] = {
    "/login": ("Sign in", "signed_out"),
    "/signup": ("Create account", "signed_out"),
    "/manage": ("Account management (signed in)", "signed_in"),
    "/downloads": ("Downloads (signed in)", "signed_in"),
    "/invite": ("Invite", "signed_out"),
    "/auth/reset-password": ("Reset password", "signed_out"),
    "/auth/verify-email": ("Verify email", "signed_out"),
    "/check-inbox": ("Check inbox", "signed_out"),
    "/app-stopped-waiting": ("App stopped", "signed_out"),
}

# The plain HTML documents in the frontend's public/ directory, served as-is.
DOC_PAGES: dict[str, str] = {
    "/terms-of-service": "Terms of service",
    "/privacy-policy": "Privacy policy",
    "/code-of-conduct": "Code of conduct",
}

# Routes the SPA's fallback component (AuthPage) serves: index.ts maps every
# path missing from PAGE_BY_PATH to it, and these are the two it is linked at.
FALLBACK_ROUTES = ("/login", "/signup")

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# A page path becomes a directory under each side of the site, so it is held to
# plain route segments (no dots, no empty segments).
PAGE_PATTERN = re.compile(r"^(?:/[a-z0-9][a-z0-9_-]*)+$")


class PreviewError(Exception):
    """A failure the CLI reports on stderr and exits non-zero for."""


def page_label(path: str) -> str:
    if path in DOC_PAGES:
        return DOC_PAGES[path]
    return PAGE_CATALOG.get(path, (path, "signed_out"))[0]


def page_state(path: str) -> str:
    """The API state a page is captured in: ``signed_out``, ``signed_in``, or ``doc``."""
    if path in DOC_PAGES:
        return "doc"
    return PAGE_CATALOG.get(path, (path, "signed_out"))[1]


def page_dir_name(path: str) -> str:
    """The directory a page is written to under a side: ``/auth/verify-email`` -> ``auth/verify-email``."""
    if not PAGE_PATTERN.fullmatch(path):
        raise PreviewError(
            f"page {path!r} is not a plain route like /login or /auth/verify-email"
        )
    return path.strip("/")


def program_name(name: str) -> str:
    """The supervisord program for preview ``name``.

    Underscored, because the workspace reserves hyphenated program names for
    apps whose manifest sits under system/apps/ (see the hosting module).
    """
    return name.replace("-", "_")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Workspace:
    """Every path the skill touches, derived from the workspace root."""

    def __init__(self, root: Path, mngr_repo: Path | None = None) -> None:
        self.root = root.absolute()
        self.mngr_repo = (
            mngr_repo or self.root / ".external_worktrees" / "mngr"
        ).absolute()

    @property
    def frontend(self) -> Path:
        return self.mngr_repo / FRONTEND_PATH

    @property
    def apps_registry(self) -> Path:
        return self.root / "data" / ".state" / "apps.toml"

    @property
    def share_env(self) -> Path:
        return self.root / "data" / ".secrets" / "share.env"

    @property
    def grants_file(self) -> Path:
        return self.root / "data" / ".secrets" / "share_grants.toml"

    @property
    def supervisord_dropins(self) -> Path:
        return self.root / "system" / "supervisord.conf.d"

    @property
    def scratch(self) -> Path:
        return self.root / "data" / ".tasks" / SKILL_NAME

    def app_dir(self, name: str) -> Path:
        return self.root / "data" / ".apps" / name

    def site_dir(self, name: str) -> Path:
        return self.app_dir(name) / "site"

    def build_dir(self, name: str, side: str) -> Path:
        return self.app_dir(name) / "builds" / side

    def state_path(self, name: str) -> Path:
        return self.app_dir(name) / "state.json"

    def conf_path(self, name: str) -> Path:
        return self.supervisord_dropins / f"{program_name(name)}.conf"

    def load_state(self, name: str) -> dict[str, Any]:
        path = self.state_path(name)
        if not path.is_file():
            return {"name": name}
        return json.loads(path.read_text())

    def save_state(self, name: str, state: dict[str, Any]) -> None:
        path = self.state_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = utc_now()
        temp = path.with_name(f".{path.name}.tmp")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.replace(temp, path)

    def update_state(self, name: str, **fields: Any) -> dict[str, Any]:
        state = self.load_state(name)
        state.update(fields)
        self.save_state(name, state)
        return state


# The modules below are code, so they load from the checkout this skill runs
# from (DEFAULT_ROOT), never from a --root pointed elsewhere for its data.


def load_forward_port() -> ModuleType:
    """The workspace's registration script, loaded by path (it is stdlib-only and not a package)."""
    return _load_module(
        "_forward_port", DEFAULT_ROOT / "system" / "scripts" / "forward_port.py"
    )


def load_grants_module() -> ModuleType:
    """The share gateway's grants module (stdlib-only), so this skill writes grants exactly as the gateway does."""
    return _load_module(
        "_share_gateway_grants",
        DEFAULT_ROOT
        / "system"
        / "services"
        / "share_gateway"
        / "src"
        / "share_gateway"
        / "grants.py",
    )


def load_claude_p() -> ModuleType:
    return _load_module(
        "_claude_p",
        DEFAULT_ROOT
        / ".agents"
        / "skills"
        / "use-ai-integration"
        / "scripts"
        / "claude_p.py",
    )


def _load_module(module_name: str, path: Path) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    if not path.is_file():
        raise PreviewError(f"missing {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PreviewError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def validate_name(name: str) -> None:
    if (
        not NAME_PATTERN.fullmatch(name)
        or not name.endswith("-preview")
        or name == "-preview"
    ):
        raise PreviewError(
            f"invalid preview name {name!r}: use kebab-case ending in -preview, e.g. 'studio-wordmark-preview'"
        )
    problem = load_forward_port().validate_service_name(name)
    if problem is not None:
        raise PreviewError(problem)


def is_owned(ws: "Workspace", name: str) -> bool:
    """Whether ``data/.apps/<name>/`` is a preview this skill made (its state carries the skill's marker)."""
    return ws.load_state(name).get("skill") == SKILL_NAME


def claim_name(ws: "Workspace", name: str) -> None:
    """Refuse a name some other app already uses; a preview this skill made may be re-run."""
    if is_owned(ws, name):
        return
    taken: list[str] = []
    if name in _registry_names(ws.apps_registry):
        taken.append(f"it is registered in {ws.apps_registry}")
    if ws.app_dir(name).exists():
        taken.append(f"{ws.app_dir(name)} already exists")
    for conf in {ws.supervisord_dropins / f"{name}.conf", ws.conf_path(name)}:
        if conf.exists():
            taken.append(f"{conf} already exists")
    if taken:
        raise PreviewError(
            f"the name {name!r} is taken ({'; '.join(taken)}); pick another --name"
        )
    ws.update_state(name, skill=SKILL_NAME)


def require_owned(ws: "Workspace", name: str) -> None:
    if not is_owned(ws, name):
        raise PreviewError(
            f"there is no preview named {name!r} made by this skill -- run the pages step first"
        )


def _registry_names(registry: Path) -> set[str]:
    if not registry.is_file():
        return set()
    return {
        str(app.get("name"))
        for app in tomllib.loads(registry.read_text()).get("apps", [])
    }


def git(
    repo: Path, *args: str, check: bool = True, extra_config: tuple[str, ...] = ()
) -> str:
    config_args: list[str] = []
    for entry in extra_config:
        config_args += ["-c", entry]
    proc = subprocess.run(
        ["git", *config_args, "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise PreviewError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def resolve_commit(repo: Path, ref: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{ref}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise PreviewError(
            f"unknown git ref {ref!r} in {repo} (run the fetch step first?)"
        )
    return proc.stdout.strip()


def read_registry_label(registry: Path, name: str) -> str | None:
    """The origin label (``<name>-<rand>``) the registry minted for app ``name``."""
    if not registry.is_file():
        return None
    data = tomllib.loads(registry.read_text())
    for app in data.get("apps", []):
        if app.get("name") == name:
            label = app.get("label")
            return str(label) if label else None
    return None


def read_share_domain(share_env: Path) -> str | None:
    if not share_env.is_file():
        return None
    for line in share_env.read_text().splitlines():
        match = re.match(r"^\s*(?:export\s+)?SHARE_WORKSPACE_DOMAIN=(.*)$", line)
        if match:
            return match.group(1).strip().strip("'\"") or None
    return None
