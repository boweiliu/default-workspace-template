"""Themes put into an app's pages from outside (docs/system/blueprint/workspace-themes/, section 7.2).

An app that does not wear the workspace's theme itself (one the `build-app` skill makes) gets it from the proxy in
front of it, which puts the page kit at the top of each page and sends ``/__workspace_theme/`` to the shell. What
the theme reaches there depends on the app's theme level:

- light: only controls the app left unstyled (no class, no style attribute) take the theme's control styles, over
  the browser's look, a CSS reset's, or the app's own rules for bare elements;
- medium: every control and the page take the theme's styles, in a cascade layer the page's own styles beat;
- heavy: the same, marked important, so the theme's values win and the app keeps only what the theme does not set.

At none nothing is put in; under the standard theme the page kit puts nothing on the page either.
"""

import itertools
import re
from collections.abc import Sequence
from typing import Final
from urllib.parse import quote

import tinycss2
from imbue.imbue_common.pure import pure
from tinycss2 import ast

from workspace_themes.contract import (
    BARE_CONTROLS_BY_PART,
    BUNDLE_FILE_NAME,
    GROUPING_AT_RULES,
    INJECTED_ROUTE_PREFIX,
    INJECTED_THEME_LAYER,
    STYLE_FILE_SUFFIX,
    UNSTYLED_ELEMENT_GUARD,
)
from workspace_themes.data_types import ThemeCatalog, ThemeEntry
from workspace_themes.errors import ThemeFileNotFoundError
from workspace_themes.primitives import ThemeLevel
from workspace_themes.serving import (
    ThemeAsset,
    ThemeBundle,
    ThemeFile,
    ThemeStyleFile,
    find_theme_file,
    read_theme_style_file,
    style_text_to_serve,
    theme_file_path,
)

INJECTED_THEMES_ROUTE_PREFIX: Final[str] = f"{INJECTED_ROUTE_PREFIX}themes/"
INJECTED_BASE_FILE_NAME: Final[str] = "base.css"
INJECTED_KIT_FILE_NAME: Final[str] = "kit.js"
INJECTED_LAYERS_FILE_NAME: Final[str] = "layers.css"
# The global the page kit reads its level from, set ahead of the kit's own script.
KIT_LEVEL_GLOBAL: Final[str] = "__WORKSPACE_THEME_LEVEL__"
_ROOT_SELECTOR: Final[str] = ":root"
_PART_ATTRIBUTE_SELECTOR: Final[re.Pattern[str]] = re.compile(
    r"\[\s*data-part\s*=\s*([\"']?)([A-Za-z0-9._-]+)\1\s*\]"
)


@pure
def _bare_control_selectors(selector: str, level: ThemeLevel) -> list[str]:
    """The selector again for each bare control that takes the control parts it names; none when it names none."""
    guard = UNSTYLED_ELEMENT_GUARD if level == ThemeLevel.LIGHT else ""
    pieces: list[tuple[str, ...]] = []
    end = 0
    is_naming_a_control = False
    for match in _PART_ATTRIBUTE_SELECTOR.finditer(selector):
        pieces.append((selector[end : match.start()],))
        controls = BARE_CONTROLS_BY_PART.get(match.group(2))
        if controls is None:
            pieces.append((match.group(0),))
        else:
            pieces.append(tuple(f"{control}{guard}" for control in controls))
            is_naming_a_control = True
        end = match.end()
    if not is_naming_a_control:
        return []
    pieces.append((selector[end:],))
    return ["".join(combination) for combination in itertools.product(*pieces)]


def _split_selector_list(prelude: Sequence[ast.Node]) -> list[str]:
    selectors: list[list[ast.Node]] = [[]]
    for token in prelude:
        if isinstance(token, ast.LiteralToken) and token.value == ",":
            selectors.append([])
        else:
            selectors[-1].append(token)
    return [tinycss2.serialize(selector).strip() for selector in selectors]


def _declarations(content: Sequence[ast.Node]) -> list[ast.Declaration]:
    return [
        node
        for node in tinycss2.parse_declaration_list(
            content, skip_comments=True, skip_whitespace=True
        )
        if isinstance(node, ast.Declaration)
    ]


def _declaration_block(
    declarations: Sequence[ast.Declaration], is_important: bool
) -> list[ast.Node]:
    marker = " !important" if is_important else ""
    text = "".join(
        f"{declaration.name}: {tinycss2.serialize(declaration.value).strip()}{marker}; "
        for declaration in declarations
    )
    return tinycss2.parse_component_value_list(text)


def _unwrap_layers(rules: Sequence[ast.Node]) -> list[ast.Node]:
    """The rules with each `@layer name { ... }` block replaced by the rules inside it."""
    unwrapped: list[ast.Node] = []
    for rule in rules:
        if (
            isinstance(rule, ast.AtRule)
            and rule.lower_at_keyword == "layer"
            and rule.content is not None
        ):
            unwrapped.extend(_unwrap_layers(tinycss2.parse_rule_list(rule.content)))
        else:
            unwrapped.append(rule)
    return unwrapped


def _rule_at_level(
    rule: ast.QualifiedRule, level: ThemeLevel
) -> ast.QualifiedRule | None:
    selectors = _split_selector_list(rule.prelude)
    bare = [
        form
        for selector in selectors
        for form in _bare_control_selectors(selector, level)
    ]
    if level == ThemeLevel.LIGHT:
        if bare:
            rule.prelude = tinycss2.parse_component_value_list(", ".join(bare) + " ")
            return rule
        # The theme's tokens, which the light level's control rules read; nothing else of the root's.
        if all(selector.startswith(_ROOT_SELECTOR) for selector in selectors):
            tokens = [
                declaration
                for declaration in _declarations(rule.content)
                if declaration.name.startswith("--")
            ]
            if not tokens:
                return None
            rule.content = _declaration_block(tokens, is_important=False)
            return rule
        return None
    if bare:
        rule.prelude = tinycss2.parse_component_value_list(
            ", ".join([*selectors, *bare]) + " "
        )
    if level == ThemeLevel.HEAVY:
        rule.content = _declaration_block(
            _declarations(rule.content), is_important=True
        )
    return rule


def _rules_at_level(rules: Sequence[ast.Node], level: ThemeLevel) -> list[ast.Node]:
    kept: list[ast.Node] = []
    for rule in _unwrap_layers(rules):
        if isinstance(rule, ast.QualifiedRule):
            leveled = _rule_at_level(rule, level)
            if leveled is not None:
                kept.append(leveled)
        elif (
            isinstance(rule, ast.AtRule)
            and rule.lower_at_keyword in GROUPING_AT_RULES
            and rule.content is not None
        ):
            nested = _rules_at_level(tinycss2.parse_rule_list(rule.content), level)
            if any(
                isinstance(node, (ast.QualifiedRule, ast.AtRule)) for node in nested
            ):
                rule.content = tinycss2.parse_component_value_list(
                    tinycss2.serialize(nested)
                )
                kept.append(rule)
        else:
            kept.append(rule)
    return kept


def style_text_at_level(css_text: str, level: ThemeLevel) -> str:
    """A style sheet as an app's page takes it at ``level``: its control rules also, or (light) only, styling the
    page's bare controls; every declaration important at heavy."""
    return tinycss2.serialize(
        _rules_at_level(tinycss2.parse_stylesheet(css_text), level)
    )


@pure
def injected_bundle_css(entry: ThemeEntry, level: ThemeLevel) -> str:
    """The theme's bundle at ``level``: the page kit's standard look, then every style file of the theme's chain.

    Medium and heavy import them into the theme's cascade layer, which the injected layer order puts above a CSS
    reset and below the page's own styles; light imports them unlayered, so its rules for unstyled controls beat a
    reset's and the app's bare-element rules by weight.
    """
    layer = (
        f" layer({INJECTED_THEME_LAYER})"
        if level in (ThemeLevel.MEDIUM, ThemeLevel.HEAVY)
        else ""
    )
    query = f"level={level}"
    lines = [
        f"/* {entry.id} ({' > '.join(entry.chain)}), revision {entry.revision}, level {level} */",
        f'@import url("../../{INJECTED_BASE_FILE_NAME}?{query}"){layer};',
    ]
    for style_file in entry.style_files:
        url = f"../{quote(style_file.theme_id)}/{quote(style_file.path)}?v={entry.revision}&{query}"
        lines.append(f'@import url("{url}"){layer};')
    return "\n".join(lines) + "\n"


def resolve_injected_theme_asset(
    catalog: ThemeCatalog, request_path: str, level: ThemeLevel | None
) -> ThemeAsset:
    """The answer to ``GET /__workspace_theme/themes/<request_path>[?level=<level>]``; raises ThemeFileNotFoundError
    when there is none. Only the bundle and a style file are cut to a level, so only they need one: a file a style
    file names by a relative ``url()`` (a library's button picture) is fetched with no query at all."""
    entry, relative = find_theme_file(catalog, request_path)
    path = None if relative == BUNDLE_FILE_NAME else theme_file_path(entry, relative)
    if path is not None and path.suffix.lower() != STYLE_FILE_SUFFIX:
        return ThemeFile(path=path)
    if level is None:
        raise ThemeFileNotFoundError(f"{request_path} is cut to a level, and the request names none")
    if path is None:
        return ThemeBundle(css=injected_bundle_css(entry, level))
    served = style_text_to_serve(
        read_theme_style_file(path),
        str(entry.id),
        relative.rpartition("/")[0],
        INJECTED_THEMES_ROUTE_PREFIX,
    )
    return ThemeStyleFile(path=path, css=style_text_at_level(served, level))


def parse_theme_level(value: str | None) -> ThemeLevel:
    """The level a request names; raises ThemeFileNotFoundError for none, or for a level that puts nothing in."""
    try:
        level = ThemeLevel(value or "")
    except ValueError:
        raise ThemeFileNotFoundError(f"{value!r} is not a theme level") from None
    if level == ThemeLevel.NONE:
        raise ThemeFileNotFoundError(
            "nothing of a theme is put into a page at level none"
        )
    return level


@pure
def injected_kit_script(kit_script: str, level: ThemeLevel) -> str:
    """The page kit's script for an app at ``level``: nothing at none, else the kit with its level set ahead of it."""
    if level == ThemeLevel.NONE:
        return ""
    return f'self.{KIT_LEVEL_GLOBAL} = "{level}";\n{kit_script}'
