- **Python floor:** every skill's scripts are type-checked by the root project, and the skill projects require Python 3.12.

- **update-self on an older Python:** the staged `update_self.py` now checks the interpreter before importing anything. On a workspace whose system Python is older than 3.12 (a local workspace from before 2026-09-14), it exits with code 75 and says the update is impossible. Step 3a then treats that as a migration-required update and offers `migrate-workspace`.

- **Migration reference:** a new section on fixing ty errors in a workspace's own scripts.

- **Syncing after a merge:** after merging a worker's branch that changed a `pyproject.toml` or `uv.lock` (such as a newly crystallized skill's `python/` project), the lead now runs `uv sync --all-packages --frozen`, so the new package is installed before anything runs it with `uv run --no-sync`. `running-python.md` lists this case.

- **Harnesses without a session-start sync:** `running-python.md` now says only claude sessions sync at start, and that agents on other harnesses sync themselves after a `pyproject.toml` or `uv.lock` change.

- **Ledger pointers:** publish-template, update-installed-template and update-published-template point at `update-self`'s `python/update_self_skill/update_ledger.py` for the exact `VERSION_HISTORY.md` starter block, instead of the `scripts/update_self.py` entry stub.
