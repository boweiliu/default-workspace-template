from pathlib import Path

import pytest

from workspace_themes.catalog import default_theme_roots, read_theme_catalog
from workspace_themes.contract import (
    BUILTIN_THEMES_DIRECTORY,
    GENERATED_ICONS_DIRECTORY,
)
from workspace_themes.errors import ThemeFileNotFoundError
from workspace_themes.injection import (
    injected_kit_script,
    parse_theme_level,
    resolve_injected_theme_asset,
    style_text_at_level,
)
from workspace_themes.primitives import ThemeLevel
from workspace_themes.serving import ThemeBundle, ThemeStyleFile
from workspace_themes.testing import write_standard_theme, write_test_theme

_CONTROL_RULES = (
    '[data-part="button"][data-variant="primary"]:hover, [data-part="tile"] { color: red; }\n'
    "code { font-family: monospace; }\n"
    ":root { --c-bg: #ffffff; background: red; }\n"
    '@media (min-width: 1px) { [data-part="field"] { color: blue; } [data-part="tile"] { color: green; } }\n'
)
_TEXT_INPUT = (
    ':is(input):where([type="text"], [type="search"], [type="email"], [type="url"], [type="password"], '
    '[type="number"], [type="tel"], :not([type]))'
)


def test_the_light_level_dresses_only_unstyled_controls_and_keeps_only_the_theme_s_tokens() -> (
    None
):
    served = style_text_at_level(_CONTROL_RULES, ThemeLevel.LIGHT)

    assert (
        ':is(button):not([class]):not([style])[data-variant="primary"]:hover {'
        in served
    )
    assert (
        f"{_TEXT_INPUT}:not([class]):not([style]), :is(textarea):not([class]):not([style]) {{"
        in served
    )
    assert "--c-bg: #ffffff;" in served
    assert "data-part" not in served
    assert "code" not in served
    assert "background" not in served
    assert "green" not in served


def test_the_medium_level_adds_every_control_to_its_part_s_rule_and_keeps_every_rule() -> (
    None
):
    served = style_text_at_level(_CONTROL_RULES, ThemeLevel.MEDIUM)

    assert (
        '[data-part="button"][data-variant="primary"]:hover, [data-part="tile"], '
        ':is(button)[data-variant="primary"]:hover {'
    ) in served
    assert "code { font-family: monospace; }" in served
    assert "!important" not in served


def test_the_heavy_level_marks_every_declaration_important() -> None:
    served = style_text_at_level(_CONTROL_RULES, ThemeLevel.HEAVY)

    assert "color: red !important;" in served
    assert "font-family: monospace !important;" in served
    assert "--c-bg: #ffffff !important;" in served


def test_a_layered_style_sheet_is_taken_out_of_its_layer() -> None:
    served = style_text_at_level(
        '@layer workspace-page-kit { [data-part="button"] { color: red; } }',
        ThemeLevel.MEDIUM,
    )

    assert "@layer" not in served
    assert '[data-part="button"], :is(button) {' in served


def _catalog(tmp_path: Path):
    write_standard_theme(tmp_path)
    folder = write_test_theme(
        tmp_path / BUILTIN_THEMES_DIRECTORY,
        "paper",
        ':root { --desk-default-wallpaper: url("assets/sky.svg"); }\n[data-part="button"] { color: red; }\n',
    )
    (folder / "assets").mkdir()
    (folder / "assets" / "sky.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>\n', encoding="utf-8"
    )
    return read_theme_catalog(
        default_theme_roots(tmp_path), {}, tmp_path / GENERATED_ICONS_DIRECTORY
    )


def test_the_bundle_imports_the_kit_s_look_then_the_theme_into_the_theme_layer_at_medium_and_heavy(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)

    medium = resolve_injected_theme_asset(catalog, "paper/theme.css", ThemeLevel.MEDIUM)
    light = resolve_injected_theme_asset(catalog, "paper/theme.css", ThemeLevel.LIGHT)

    assert isinstance(medium, ThemeBundle) and isinstance(light, ThemeBundle)
    assert (
        '@import url("../../base.css?level=medium") layer(workspace-theme);'
        in medium.css
    )
    assert medium.css.splitlines()[-1].endswith(
        '&level=medium") layer(workspace-theme);'
    )
    assert '@import url("../../base.css?level=light");' in light.css
    assert "layer(" not in light.css


def test_a_style_file_sends_its_token_urls_from_the_injected_route_at_its_level(
    tmp_path: Path,
) -> None:
    asset = resolve_injected_theme_asset(
        _catalog(tmp_path), "paper/parts.css", ThemeLevel.LIGHT
    )

    assert isinstance(asset, ThemeStyleFile)
    assert 'url("/__workspace_theme/themes/paper/assets/sky.svg")' in asset.css
    assert ":is(button):not([class]):not([style]) {" in asset.css


@pytest.mark.parametrize("value", [None, "", "none", "ultra"])
def test_a_request_without_a_level_that_puts_something_in_is_not_found(
    value: str | None,
) -> None:
    with pytest.raises(ThemeFileNotFoundError):
        parse_theme_level(value)


def test_the_kit_carries_its_level_and_is_empty_at_none() -> None:
    assert injected_kit_script("kit();", ThemeLevel.NONE) == ""
    assert (
        injected_kit_script("kit();", ThemeLevel.LIGHT)
        == 'self.__WORKSPACE_THEME_LEVEL__ = "light";\nkit();'
    )
