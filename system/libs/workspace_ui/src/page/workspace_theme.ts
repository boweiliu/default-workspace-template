/**
 * The page kit's script (docs/system/blueprint/workspace-themes/, section 7.2), built as one classic script that the
 * proxy in front of an app puts at the top of each of its pages, served from `/__workspace_theme/kit.js` with the
 * app's theme level set ahead of it. From then on the page wears the workspace's theme at that level: the theme this
 * origin last wore before the first paint, then whatever the shell names in `shell:theme`. The standard theme puts
 * nothing on the page, so an app looks as it was built until another theme is worn.
 */

import "./workspace_theme.css";
import { followShellTheme } from "../app_contract";
import { STANDARD_THEME_ID } from "../themes/themeBoot";
import { rememberedTheme, wearTheme, wearThemeFromMessage, type ThemeRef } from "../themes/themeClient";

const INJECTED_THEMES_PREFIX = "/__workspace_theme/themes/";
const level = (globalThis as { __WORKSPACE_THEME_LEVEL__?: unknown }).__WORKSPACE_THEME_LEVEL__;

if (typeof level === "string") {
  const bundleUrl = (theme: ThemeRef): string | null => {
    if (theme.id === STANDARD_THEME_ID) return null;
    const revision = theme.revision === "" ? "" : `v=${encodeURIComponent(theme.revision)}&`;
    return `${INJECTED_THEMES_PREFIX}${encodeURIComponent(theme.id)}/theme.css?${revision}level=${encodeURIComponent(level)}`;
  };
  const remembered = rememberedTheme();
  // Put on while <head> is still being read, so holding the first frame until it loads costs no flash.
  if (remembered.id !== STANDARD_THEME_ID) void wearTheme(remembered, document, { isRenderBlocking: true, bundleUrl });
  followShellTheme(
    (theme, revision, isPreview) => void wearThemeFromMessage({ theme, revision, isPreview }, { bundleUrl }),
  );
}
