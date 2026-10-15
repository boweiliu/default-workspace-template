"""Everything this app asks of Imbue Studio, as HTTP calls.

The app shares no code with the workspace it runs in. What it needs from Studio
it gets over loopback HTTP from the workspace shell (the ``system_interface``
server). Every route used here is listed in ``docs/studio-contract.md``.
"""

import os
import threading
import urllib.error
import urllib.request

# The workspace shell. Studio's own code reads the same variable for the same address.
SHELL_URL = os.environ.get("MINDS_WORKSPACE_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")

# The browser modules every app page imports from its own origin: the app contract (how a page talks to the
# shell framing it) and the element context menu. The shell serves them at /_static/<name>, but a browser
# cannot import them cross-origin (the forwarder refuses cookieless cross-origin module fetches), so this app
# fetches them server-side and re-serves them.
SHELL_MODULE_NAMES = ("app_contract.js", "context_menu.js")

_FETCH_TIMEOUT_SECONDS = 5.0


class ShellUnavailableError(Exception):
    """The shell could not be reached, or did not have what was asked for."""


_module_cache: dict[str, bytes] = {}
_module_cache_lock = threading.Lock()


def fetch_shell_module(name: str) -> bytes:
    """Return one of the shell's browser modules, fetched once and then kept for the life of the process.

    A module the shell changes reaches this app at its next restart, the same moment it reaches an in-tree app
    (whose copy is read from the shell's build output when the app starts serving).
    """
    if name not in SHELL_MODULE_NAMES:
        raise KeyError(name)
    with _module_cache_lock:
        cached = _module_cache.get(name)
    if cached is not None:
        return cached
    url = f"{SHELL_URL}/_static/{name}"
    try:
        with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            body = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ShellUnavailableError(f"GET {url} failed: {error}") from error
    with _module_cache_lock:
        _module_cache[name] = body
    return body


def clear_module_cache() -> None:
    with _module_cache_lock:
        _module_cache.clear()
