- `system/test_no_type_errors.py` type-checks the root project with ty: the skills and their shared scripts, `system/scripts`, the root-level tests and `conftest.py`. It also checks the bare tier (what the system `python3` runs) a second time, against an environment with no third-party packages. There, an import the system `python3` could not make at runtime shows up as `unresolved-import`, at Python 3.12. This replaces `stdlib_only_scripts_test.py`, and fixes the errors the new check found.

- The workspace's Python floor is 3.12: `requires-python = ">=3.12"` in the root and every project, and ruff and pyright target 3.12. The build no longer installs a uv-managed 3.12 or pins `UV_PYTHON`, because with no project allowing 3.11, uv can no longer settle on a system 3.11 that the lock rejects: it uses an interpreter that satisfies `>=3.12`, downloading one when the system has none.

- Local workspaces from before 2026-09-14 (Debian 12, system Python 3.11) can no longer be updated in place (see the update-self change).

- A worker's provision-time sync is `--frozen`, so a lock that drifted from `pyproject.toml` is regenerated only by the worker's SessionStart hook, which tells the agent to commit it. The root launch rules also read supervisord program lines the way supervisord does (`command = ...`, `bash -lc "..."`), and a bare-tier file that imports venv-tier first-party code (such as `workspace_scripts`) now fails a root test.

- The `bootstrap` window puts the root venv's `bin` dir first on `PATH` and sets `VIRTUAL_ENV` before it starts supervisord, as `uv run bootstrap` used to. Without that, programs that name a console script by bare name (an app scaffolded by build-app) could not find it. A root test runs the window's command and checks this.

- The workspace-app contract (`contracts.md` section 14) now says a pre-manifest app and the background services run from `.venv/bin/<name>`, not under `uv run`, matching the launch rule.
