"""The SessionStart sync relocks only a drifted lock, says so once, and always syncs frozen."""

import os
import subprocess
from pathlib import Path

_HOOK = Path(__file__).resolve().with_name("session_start_sync.sh")

_PYPROJECT = """\
[project]
name = "session-start-sync-probe"
version = "0.1.0"
requires-python = "{requires_python}"
dependencies = [{dependencies}]

[tool.uv]
package = false
"""


def _project(root: Path, requires_python: str, dependencies: str = "") -> None:
    (root / "pyproject.toml").write_text(
        _PYPROJECT.format(requires_python=requires_python, dependencies=dependencies)
    )


def _run_hook(root: Path) -> subprocess.CompletedProcess[str]:
    # Offline: the probe project has no dependencies, so nothing here needs an index.
    return subprocess.run(
        ["bash", str(_HOOK)],
        cwd=root,
        env={**os.environ, "UV_OFFLINE": "1", "VIRTUAL_ENV": ""},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_an_in_sync_lock_syncs_silently(tmp_path: Path) -> None:
    _project(tmp_path, ">=3.11")
    subprocess.run(["uv", "lock", "--quiet"], cwd=tmp_path, check=True, timeout=120)
    lock_before = (tmp_path / "uv.lock").read_text()

    result = _run_hook(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert (tmp_path / "uv.lock").read_text() == lock_before
    assert (tmp_path / ".venv").is_dir()


def test_a_drifted_lock_is_regenerated_and_the_agent_told_to_commit_it(
    tmp_path: Path,
) -> None:
    _project(tmp_path, ">=3.11")
    subprocess.run(["uv", "lock", "--quiet"], cwd=tmp_path, check=True, timeout=120)
    _project(tmp_path, ">=3.12")

    result = _run_hook(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (
        "uv.lock was out of date with pyproject.toml and has been regenerated"
        in result.stdout
    )
    assert len(result.stdout.splitlines()) == 1
    assert 'requires-python = ">=3.12"' in (tmp_path / "uv.lock").read_text()
    subprocess.run(
        ["uv", "lock", "--check"],
        cwd=tmp_path,
        check=True,
        timeout=120,
        capture_output=True,
    )
    assert (tmp_path / ".venv").is_dir()


def test_a_lock_that_cannot_be_regenerated_is_left_alone_and_said_so(
    tmp_path: Path,
) -> None:
    _project(tmp_path, ">=3.11")
    subprocess.run(["uv", "lock", "--quiet"], cwd=tmp_path, check=True, timeout=120)
    lock_before = (tmp_path / "uv.lock").read_text()
    # Offline, a dependency that is in no cache cannot resolve, so the relock fails.
    _project(tmp_path, ">=3.11", '"no-such-package-for-session-start-sync"')

    result = _run_hook(tmp_path)

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 1
    assert "failed to regenerate it" in result.stdout
    assert "has been regenerated" not in result.stdout
    assert (tmp_path / "uv.lock").read_text() == lock_before
    assert (tmp_path / ".venv").is_dir()
