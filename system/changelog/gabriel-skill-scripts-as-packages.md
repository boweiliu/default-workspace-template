This release turns the workspace's scripts into packages. An existing workspace's own skills, services and docs are migrated during the update by following `.agents/skills/update-self/references/python-packaging-migration.md`.

- `system/scripts` is one uv project with two packages. `workspace_bare_scripts` runs under the system `python3` with no venv and imports only the standard library. `workspace_scripts` (the changelog gate, the docs viewer, the auth migration, the view refresh and the app smoketest) runs from the root venv.

- Every existing script path stays as a thin entry file that imports its package. Only the five hook entry files that reach the `tk_command_parsing` or `oom_priority` source tree still edit `sys.path`, along with the skill entry files that run with no venv (update-self's, and publish-template's two manifest tools).

- The root workspace adds the `system/scripts`, `.agents/shared/scripts` and `.agents/skills/*/python` members, so skill dependencies resolve in the one `uv.lock`.

- The CI changelog job runs the gate from a `uv sync --frozen --package workspace-scripts` venv.

- New root checks:
  - `system/test_entry_point_import_cost.py` fails an entry point that loads pydantic, loguru, click, tenacity, httpx or asyncio at import without declaring it.
  - `system/test_external_entry_paths.py` runs every path that Imbue Studio, CI and older update-self releases call by path, with no site-packages.
  - `system/test_python_launch_rules.py` fails a `python3 <path>.py` that names a venv-tier or missing script. It also counts the code that edits `sys.path` and the code that loads a module from a file path (`spec_from_file_location`, `SourceFileLoader`, `runpy.run_path`), tests included, and fails when either count rises.
  - The plain-`uv run` check no longer reads files that link into `system/vendor/`. Once the mngr assets were fetched, `docs/system/style_guide.md` resolved to mngr's style guide and failed the check inside a workspace.
  - `system/test_meta_ratchets.py` requires a `pyproject.toml` in every skill `python/` dir. Without one, every `uv` command in the workspace fails.

- The bug-report collector runs as a `Collector` object that takes its container paths and class budgets as arguments. Its tests build one per test instead of loading a fresh copy of the module by path. What the collector collects is unchanged.

- The supervisord program readers in `system/test_app_manifests.py` and `system/test_supervisord_layout.py` share one helper, `oom_priority.testing.supervisord_commands`, instead of loading each other's test files by path.
