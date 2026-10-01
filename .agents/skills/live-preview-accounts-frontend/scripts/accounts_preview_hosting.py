"""Host, share, and tear down one preview app.

A preview app is deliberately light: a supervisord program running Python's
standard-library static file server over ``data/.apps/<name>/site/``, which
registers itself (``forward_port.py --name``) so it gets its own origin and
its own share scope. It has no folder under ``system/apps/``: every folder
there must be a Python package (a manifest-only folder breaks the workspace's
``uv`` workspace), and a package per preview would churn the shared lockfile.
Its program name is underscored (``studio_wordmark_preview``) because the
workspace's guard tests reserve hyphenated program names for apps that do have
a manifest there; the app's registered name, origin, and share scope keep the
hyphenated preview name.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from accounts_preview_common import (
    DEFAULT_ROOT,
    PROD_BASE,
    SKILL_DIR,
    PreviewError,
    Workspace,
    load_grants_module,
    page_label,
    program_name,
    read_registry_label,
    read_share_domain,
)
from accounts_preview_site import side_url

LOWEST_PORT = 8080
# Ports the template's services hold that may not appear in a drop-in's URL.
_RESERVED_PORTS = {8000, 8010, 8030, 8081}
_PORT_IN_TEXT = re.compile(r"(?:localhost|127\.0\.0\.1):(\d{2,5})|http\.server\s+(\d{2,5})")

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def ports_in_use(ws: Workspace) -> set[int]:
    """Every port a drop-in or a registry row names."""
    ports = set(_RESERVED_PORTS)
    texts = [conf.read_text() for conf in sorted(ws.supervisord_dropins.glob("*.conf"))]
    if ws.apps_registry.is_file():
        texts.append(ws.apps_registry.read_text())
    for text in texts:
        for match in _PORT_IN_TEXT.finditer(text):
            ports.add(int(match.group(1) or match.group(2)))
    return ports


def _is_bound(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def pick_port(ws: Workspace, is_bound: Callable[[int], bool] = _is_bound) -> int:
    taken = ports_in_use(ws)
    port = LOWEST_PORT
    while port in taken or is_bound(port):
        port += 1
    return port


def display_name(name: str) -> str:
    return f"Preview: {name}"[:64]


def conf_text(ws: Workspace, name: str, port: int) -> str:
    """The supervisord drop-in for preview ``name`` (paths relative to the workspace root it runs from)."""
    program = program_name(name)
    app = f"data/.apps/{name}"
    register = (
        f"python3 system/scripts/forward_port.py --name {name} --url http://localhost:{port} "
        f"--icon-file {app}/icon.svg --display-name '{display_name(name)}' --program {program}"
    )
    serve = f"exec python3 -m http.server {port} --bind 127.0.0.1 --directory {app}/site"
    return f"""; Throwaway before/after preview made by the live-preview-accounts-frontend skill.
; Remove with: uv run .agents/skills/live-preview-accounts-frontend/scripts/run.py teardown --name {name}
[program:{program}]
command=python3 system/services/oom_priority/bin/oom_tag_service.py user bash -c "{register} && {serve}"
directory={ws.root}
autostart=true
autorestart=true
startsecs=5
startretries=5
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/supervisor/{program}-stdout.log
stderr_logfile=/var/log/supervisor/{program}-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_backups=3
"""


def _wait_until_serving(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    return False


def host_preview(
    ws: Workspace,
    name: str,
    state: dict[str, Any],
    run: Runner = _run,
    wait_timeout: float = 60,
    is_serving: Callable[[str, float], bool] = _wait_until_serving,
) -> dict[str, Any]:
    """Create (first run) or confirm (re-run) the preview's program; returns ``{"port", "created"}``."""
    program = program_name(name)
    conf = ws.conf_path(name)
    if not (ws.site_dir(name) / "index.html").is_file():
        raise PreviewError(f"no rendered site for {name!r} -- run the render step first")
    created = False
    if conf.exists():
        port = state.get("port")
        if not port or f"[program:{program}]" not in conf.read_text():
            raise PreviewError(f"{conf} exists but was not made for preview {name!r}; pick another --name")
    else:
        port = pick_port(ws)
        shutil.copy2(SKILL_DIR / "assets" / "icon.svg", ws.app_dir(name) / "icon.svg")
        conf.write_text(conf_text(ws, name, port))
        created = True
        for command in (["supervisorctl", "reread"], ["supervisorctl", "update", program]):
            result = run(command)
            if result.returncode != 0:
                raise PreviewError(f"{' '.join(command)} failed: {result.stdout}{result.stderr}")
    status = run(["supervisorctl", "status", program])
    if "RUNNING" not in status.stdout:
        started = run(["supervisorctl", "start", program])
        if started.returncode != 0 and "already started" not in started.stdout:
            raise PreviewError(f"supervisorctl start {program} failed: {started.stdout}{started.stderr}")
    if not is_serving(f"http://127.0.0.1:{port}/", wait_timeout):
        raise PreviewError(
            f"the preview did not answer on port {port} within {wait_timeout:.0f}s; "
            f"see /var/log/supervisor/{program}-stderr.log"
        )
    return {"port": port, "created": created}


def public_base_url(ws: Workspace, name: str) -> str:
    domain = read_share_domain(ws.share_env)
    if domain is None:
        raise PreviewError(f"workspace sharing is not enabled ({ws.share_env} has no SHARE_WORKSPACE_DOMAIN)")
    label = read_registry_label(ws.apps_registry, name)
    if label is None:
        raise PreviewError(f"{name!r} is not registered in {ws.apps_registry} -- run the host step first")
    return f"https://{label}.{domain}"


def _load_or_empty_grants(grants: Any, path: Path) -> Any:
    if path.exists():
        return grants.load_grants(path)
    return grants.Grants(workspace=grants.GrantList([], [], []), services={})


def share_preview(ws: Workspace, name: str, email_domain: str) -> dict[str, Any]:
    """Grant ``email_domain`` access to this preview app only; a no-op when it already has it."""
    base_url = public_base_url(ws, name)
    grants = load_grants_module()
    domain = email_domain.strip().lower().lstrip("@")
    if not domain or "." not in domain:
        raise PreviewError(f"invalid email domain {email_domain!r}")
    with grants.locked_grants_file(ws.grants_file):
        document = _load_or_empty_grants(grants, ws.grants_file)
        scope = document.services.setdefault(name, grants.GrantList([], [], []))
        changed = domain not in scope.email_domains
        if changed:
            scope.email_domains.add(domain)
            grants.write_grants_atomic(ws.grants_file, grants.render_grants(document))
    return {"url": base_url, "email_domain": domain, "changed": changed}


def unshare_preview(ws: Workspace, name: str) -> bool:
    """Drop the preview's whole ``[services.<name>]`` scope; True when there was one."""
    if not ws.grants_file.exists():
        return False
    grants = load_grants_module()
    with grants.locked_grants_file(ws.grants_file):
        document = grants.load_grants(ws.grants_file)
        if name not in document.services:
            return False
        del document.services[name]
        grants.write_grants_atomic(ws.grants_file, grants.render_grants(document))
    return True


def _registered(registry: Path, name: str) -> bool:
    if not registry.is_file():
        return False
    return any(app.get("name") == name for app in tomllib.loads(registry.read_text()).get("apps", []))


def teardown_preview(ws: Workspace, name: str, run: Runner = _run) -> list[str]:
    """Remove everything one preview made; safe to re-run. Returns what it did."""
    done: list[str] = []
    program = program_name(name)
    conf = ws.conf_path(name)
    if conf.exists():
        if f"[program:{program}]" not in conf.read_text() or "live-preview-accounts-frontend" not in conf.read_text():
            raise PreviewError(f"{conf} was not made by this skill; not removing it")
        run(["supervisorctl", "stop", program])
        conf.unlink()
        run(["supervisorctl", "reread"])
        run(["supervisorctl", "update", program])
        done.append(f"stopped and removed program {program}")
    if _registered(ws.apps_registry, name):
        result = run(
            ["env", f"MINDS_APPS_FILE={ws.apps_registry}", "python3",
             str(DEFAULT_ROOT / "system" / "scripts" / "forward_port.py"), "--remove", "--name", name]
        )
        if result.returncode != 0:
            raise PreviewError(f"unregistering {name} failed: {result.stderr}")
        done.append(f"unregistered app {name}")
    if unshare_preview(ws, name):
        done.append(f"removed share grant [services.{name}]")
    app_dir = ws.app_dir(name)
    if app_dir.exists():
        shutil.rmtree(app_dir)
        done.append(f"deleted {app_dir}")
    return done


def markdown_table(pages: list[str], base_url: str) -> str:
    """The PR-description table: one row per page, prod / before / after links."""
    base = base_url.rstrip("/")
    lines = [
        "| Page | Before (prod) | Before (preview) | After (preview) |",
        "|---|---|---|---|",
    ]
    for path in pages:
        lines.append(
            f"| {page_label(path)} | [prod]({PROD_BASE}{path}) "
            f"| [before]({base}{side_url('before', path)}) | [after]({base}{side_url('after', path)}) |"
        )
    lines += ["", f"Side-by-side overview of every page: {base}/"]
    return "\n".join(lines)

