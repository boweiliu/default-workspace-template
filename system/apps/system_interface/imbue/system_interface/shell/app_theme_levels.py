"""The theme level the user chose for each app that does not wear the workspace's theme itself (the workspace-themes
plan, section 7.2), kept in ``app_theme_levels.json`` under the shell's state directory."""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from app_manifest.manifest import ThemingMode
from app_manifest.primitives import AppName
from app_manifest.registry import RegistryRow
from pydantic import Field
from workspace_themes.primitives import ThemeLevel

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.pure import pure
from imbue.system_interface.shell.state_files import STATE_FILES_LOCK
from imbue.system_interface.shell.state_files import parse_versioned_document
from imbue.system_interface.shell.state_files import read_json_object
from imbue.system_interface.shell.state_files import write_json_atomic

APP_THEME_LEVELS_FILENAME: Final[str] = "app_theme_levels.json"
APP_THEME_LEVELS_FILE_VERSION: Final[int] = 1
DEFAULT_THEME_LEVEL: Final[ThemeLevel] = ThemeLevel.LIGHT


class AppThemeLevelsDocument(FrozenModel):
    """The whole of ``app_theme_levels.json``: the level of each app the user set one for."""

    version: int = Field(description="The file format version")
    apps: dict[AppName, ThemeLevel] = Field(description="Each app's chosen theme level, by app name")


@pure
def is_themed_from_outside(row: RegistryRow) -> bool:
    """Whether the app's pages could take the theme from outside: it declares no ``[theming]`` of its own (and is not
    themeable yet), or declares ``mode = "outside"`` (it is). Its window menu has a Theming submenu."""
    return row.theming_mode is None or row.theming_mode == ThemingMode.OUTSIDE


@pure
def is_themeable(row: RegistryRow) -> bool:
    """Whether the app is written to take the theme from outside, so the user can turn its theming on and off."""
    return row.theming_mode == ThemingMode.OUTSIDE


@pure
def theme_level_of(row: RegistryRow | None, level_by_app: Mapping[AppName, ThemeLevel]) -> ThemeLevel:
    """The level the theme is put into an app's pages at: for a themeable app, off (none) when the user turned it off
    and on (light) otherwise; none for every other app and for a service the registry does not know."""
    if row is None or not is_themeable(row) or level_by_app.get(row.name) == ThemeLevel.NONE:
        return ThemeLevel.NONE
    return DEFAULT_THEME_LEVEL


class AppThemeLevelStore(MutableModel):
    """Reads and writes ``app_theme_levels.json`` under the shell's state lock."""

    state_directory: Path = Field(frozen=True, description="The shell's state directory")

    def _path(self) -> Path:
        return self.state_directory / APP_THEME_LEVELS_FILENAME

    def _read_unlocked(self) -> dict[AppName, ThemeLevel]:
        document = parse_versioned_document(
            read_json_object(self._path()), AppThemeLevelsDocument, APP_THEME_LEVELS_FILE_VERSION, self._path()
        )
        return {} if document is None else dict(document.apps)

    def read(self) -> dict[AppName, ThemeLevel]:
        """Each app's chosen level; an app missing from it is at the default."""
        with STATE_FILES_LOCK:
            return self._read_unlocked()

    def set(self, app: AppName, level: ThemeLevel) -> dict[AppName, ThemeLevel]:
        """Record an app's level, and answer every app's."""
        with STATE_FILES_LOCK:
            levels = {**self._read_unlocked(), app: level}
            document = AppThemeLevelsDocument(version=APP_THEME_LEVELS_FILE_VERSION, apps=levels)
            write_json_atomic(self._path(), document.model_dump(mode="json"))
        return levels
