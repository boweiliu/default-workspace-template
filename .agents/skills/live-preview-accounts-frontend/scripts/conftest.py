"""The skill's scripts import each other as siblings (the directory is ``sys.path[0]``
when ``run.py`` runs); put it there for the tests too, and give every test a
scratch workspace laid out like the real one."""

import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from accounts_preview_common import Workspace  # noqa: E402

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures"
FORTRESS = Path("/opt/fortress/tilion-fortress/tilion")


@pytest.fixture(autouse=True)
def _isolate_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "workspace"
    for directory in ("data/.state", "data/.secrets", "data/.apps", "system/supervisord.conf.d"):
        (root / directory).mkdir(parents=True)
    return Workspace(root, tmp_path / "mngr")


@pytest.fixture(scope="session")
def browser():
    """One headless Fortress browser for every browser test (launching costs seconds under gVisor)."""
    if not FORTRESS.exists():
        pytest.skip("the Fortress browser is not installed")
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(executable_path=str(FORTRESS))
        yield launched
        launched.close()
